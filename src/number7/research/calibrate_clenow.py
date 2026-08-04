"""Clenow calibration runner (spec §11). Run:

    uv run python -m number7.research.calibrate_clenow

Writes docs/research/2026-08-clenow-calibration-memo.md and logs every run to the trials
ledger. Diagnostics register under DIAGNOSTIC_FAMILY so they never inflate the candidate's
DSR trial count.

ANTI-FITTING CLAUSE (spec §11.4): "a discrepancy triggers investigation, not failure" is
bounded. Legitimate: implementation bug found -> fix -> re-run. NOT legitimate: parameter
nudged until the chart matches the book. Any parameter change spawns a NEW pre-registration
and counts as a new trial."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from number7.benchmarks.ew import EqualWeightIndex, gate6
from number7.config import get_settings
from number7.data.snapshot import current_snapshot
from number7.engine.backtest import BacktestResult, run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.live import build_panel
from number7.engine.schedule import weekly_rebalances
from number7.research.ledger import Ledger
from number7.research.preregs import (CANDIDATE_FAMILY, CLENOW_DIAGNOSTIC,
                                      CLENOW_REFERENCE)
from number7.strategies.clenow import ClenowMomentum, ClenowParams
from number7.strategies.sizing import SizingConfig
from number7.validation.dsr import dsr, dsr_hurdle
from number7.validation.monkey import monkey_test
from number7.validation.montecarlo import block_bootstrap_dd
from number7.validation.walkforward import WFProtocol, walk_forward

SLEEVE_EQUITY = 50_000.0
CASH_ANNUAL_RATE = 0.0          # PINNED for primary runs (spec §11.3). We have no bill
# series in the snapshot, so a historical rate path would be fabricated. The 2%/4%
# diagnostics below quantify the handicap instead; the memo must state all three.
CASH_DIAGNOSTICS = (0.02, 0.04)
COST_MULTIPLES = (0.0, 1.0, 2.0)
MEMO = Path("docs/research/2026-08-clenow-calibration-memo.md")

# Two FROZEN profiles (spec §4), not a runtime toggle. The configuration that passes the
# gauntlet must be the configuration that ships, so both are gauntlet-run - but the
# reference profile is fidelity evidence only and is NEVER deployable evidence.
PROFILES: dict[str, tuple[ClenowParams, SizingConfig]] = {
    "reference": (
        ClenowParams(),
        SizingConfig(sleeve_equity=SLEEVE_EQUITY, position_cap=1.0,
                     min_position_dollars=0.0, gross_max=1.0, drift_band=0.0,
                     max_positions=100, forced_resize_periods=10**6),
    ),
    "deployable": (
        ClenowParams(),
        SizingConfig(sleeve_equity=SLEEVE_EQUITY, position_cap=0.10,
                     min_position_dollars=1000.0, gross_max=1.0, drift_band=0.05,
                     max_positions=30, forced_resize_periods=8),
    ),
}

ABLATIONS: dict[str, ClenowParams] = {
    "no_r2": ClenowParams(use_r2=False),
    "no_regime": ClenowParams(use_regime=False),
    "no_gap": ClenowParams(use_gap_filter=False),
    "equal_weight": ClenowParams(equal_weight=True),
}


def run_profile(panel, params: ClenowParams, sizing: SizingConfig, cost_model: CostModel,
                *, cash_annual_rate: float = CASH_ANNUAL_RATE,
                initial: float = SLEEVE_EQUITY) -> BacktestResult:
    rb = weekly_rebalances(panel.sessions)
    return run_backtest(ClenowMomentum(params), panel, rb, cost_model, sizing=sizing,
                        initial=initial, cash_annual_rate=cash_annual_rate)


def regime_episodes(panel, params: ClenowParams) -> list[dict]:
    """Every regime-off episode over the whole history, scored on hit rate and cost
    (spec §11.2.2). Resting a gate on N=1 realization of the event it exists to handle is
    not a gate."""
    spy = panel.px_close[params.regime_symbol]
    sma = spy.rolling(params.regime_ma).mean()
    off = (spy <= sma) & sma.notna()
    episodes: list[dict] = []
    idx = panel.sessions
    grp = (off != off.shift()).cumsum()
    tr = panel.tr_close[params.regime_symbol]
    for _, block in off.groupby(grp):
        if not bool(block.iloc[0]) or len(block) < 2:
            continue
        start, end = block.index[0], block.index[-1]
        fwd = idx[idx > end]
        horizon = fwd[:63]          # ~3 months forward, or what remains
        after = (float(tr.loc[horizon[-1]] / tr.loc[end] - 1.0)
                 if len(horizon) else float("nan"))
        during = float(tr.loc[end] / tr.loc[start] - 1.0)
        episodes.append({"start": str(start.date()), "end": str(end.date()),
                         "sessions": int(len(block)),
                         "index_return_through_episode": during,
                         "post_episode_return": after,          # ~3 months after re-entry
                         "hit": bool(during < 0)})
    return episodes


def exposure_metrics(result: BacktestResult, panel) -> dict:
    """Under-investment is EXPECTED (spec §8.2), so raw CAGR against a fully-invested SPY
    through a long bull punishes the design for working as intended. Gate on Sharpe, beta,
    and return per unit of average gross exposure, and report average gross exposure as a
    first-class metric (spec §11.2.3)."""
    s = summary(result)
    gross = result.weights.sum(axis=1)
    avg_gross = float(gross.mean()) if len(gross) else 0.0
    eq = result.equity.dropna()
    r = np.log(eq).diff().dropna()
    bench = np.log(panel.tr_close["SPY"]).diff().reindex(r.index).fillna(0.0)
    var_b = float(bench.var(ddof=0))
    beta = float(np.cov(r, bench, ddof=0)[0, 1] / var_b) if var_b > 0 else float("nan")
    return {"avg_gross": avg_gross,
            "return_per_unit_exposure": s["cagr"] / avg_gross if avg_gross > 0 else 0.0,
            "beta_vs_index": beta,
            "sharpe": s["sharpe"],
            "cagr": s["cagr"],
            "max_dd": s["max_dd"],
            "delisting_exits": int(result.delisting_exits.sum())}


def turnover_at_transitions(result: BacktestResult, episodes: list[dict]) -> dict:
    """Whipsaw-driven turnover spikes at SMA crossings are the known failure mode, and an
    average hides them (spec §11.2.4)."""
    marks = pd.DatetimeIndex(sorted({pd.Timestamp(e[k]) for e in episodes
                                     for k in ("start", "end")}))
    t = result.turnover
    if not len(t):
        return {"avg_turnover": 0.0, "avg_turnover_at_transitions": 0.0, "n_transitions": 0}
    near = t.index[[bool((abs(marks - d) <= pd.Timedelta(days=7)).any()) for d in t.index]]
    return {"avg_turnover": float(t.mean()),
            "avg_turnover_at_transitions": float(t.loc[near].mean()) if len(near) else 0.0,
            "n_transitions": int(len(near))}


def _code_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


def _gauntlet(panel, params, sizing, cost_model, res, label: str) -> dict:
    """Gates 2-6 for one profile. Both frozen profiles get the full run; only the
    deployable one is ever treated as deployable evidence (spec §4)."""
    rb = weekly_rebalances(panel.sessions)
    eq = res.equity.dropna()
    r = np.log(eq).diff().dropna()
    wf = walk_forward(lambda: ClenowMomentum(params), panel,
                      WFProtocol(), cost_model, sizing=sizing, initial=SLEEVE_EQUITY)
    mk = monkey_test(res, panel, rb, cost_model,
                     null_factory=lambda s: ClenowMomentum(params, shuffle_seed=s),
                     sizing=sizing, initial=SLEEVE_EQUITY, n_monkeys=1000, seed=17)
    bench = run_backtest(EqualWeightIndex(), panel, rb, cost_model, initial=SLEEVE_EQUITY)
    return {
        "label": label,
        "summary": summary(res),
        "exposure": exposure_metrics(res, panel),
        "walk_forward": {"wfe": wf.wfe, "n_windows": len(wf.windows),
                         "passes": wf.passes(WFProtocol())},
        "monkey": mk,
        "bootstrap": block_bootstrap_dd(r.to_numpy(), block=10, n=2000, seed=17),
        "gate6": gate6(summary(res), summary(bench)),
        "sharpe_per_period": float(r.mean() / r.std(ddof=0)) if r.std(ddof=0) > 0 else 0.0,
        "n_obs": int(len(r)),
        "skew": float(r.skew()), "kurt": float(r.kurt() + 3.0),
    }


def main() -> None:
    settings = get_settings()
    root = current_snapshot(settings)
    if root is None:
        raise SystemExit("no promoted snapshot: run number7.ops.nightly first")
    panel = build_panel(root)
    cost_model = CostModel()
    led = Ledger(settings.data_dir / "trials.duckdb")
    sha, snap = _code_sha(), root.name

    # CLENOW_SEARCHED is NOT registered here: this run searches nothing. Declaring a grid
    # we do not walk would misreport the degrees of freedom in exactly the direction the
    # ledger exists to prevent. The follow-on grid run registers it.
    reg_ref = led.register(CLENOW_REFERENCE)
    reg_diag = led.register(CLENOW_DIAGNOSTIC)

    report: dict = {"snapshot": snap, "code_sha": sha,
                    "cash_annual_rate": CASH_ANNUAL_RATE, "profiles": {}, "diagnostics": {}}

    for name, (params, sizing) in PROFILES.items():
        res = run_profile(panel, params, sizing, cost_model)
        g = _gauntlet(panel, params, sizing, cost_model, res, name)
        n_trials = led.family_trials(CANDIDATE_FAMILY)
        g["dsr"] = dsr(g["sharpe_per_period"], g["n_obs"], g["skew"], g["kurt"],
                       n_trials=n_trials,
                       var_trials=led.var_of_trial_sharpes(CANDIDATE_FAMILY))
        g["dsr_hurdle"] = dsr_hurdle(n_trials, CLENOW_REFERENCE.origin)
        g["dsr_passes"] = g["dsr"] >= g["dsr_hurdle"]
        # The reference profile IS the registered candidate — the one-point replication.
        # The PROFILE PAIR is a declared diagnostic (spec §10): neither profile is a
        # deployment candidate today, and the deployable profile gets its own full
        # gauntlet re-run before capital, after the risk layer exists.
        reg = reg_ref if name == "reference" else reg_diag
        led.log_run(reg, sha, snap, {"profile": name, **asdict(params)},
                    {**g["summary"], **g["exposure"], "dsr": g["dsr"]})
        report["profiles"][name] = g

    report["regime_episodes"] = regime_episodes(panel, PROFILES["deployable"][0])
    dep_params, dep_sizing = PROFILES["deployable"]
    dep_res = run_profile(panel, dep_params, dep_sizing, cost_model)
    report["turnover"] = turnover_at_transitions(dep_res, report["regime_episodes"])

    # --- diagnostics: excluded from the DSR trial count by construction (own family) ---
    for name, params in ABLATIONS.items():
        res = run_profile(panel, params, dep_sizing, cost_model)
        m = exposure_metrics(res, panel)
        led.log_run(reg_diag, sha, snap, {"ablation": name}, {**summary(res), **m})
        report["diagnostics"][f"ablation_{name}"] = m
    for mult in COST_MULTIPLES:
        cm = CostModel(commission_bps=CostModel().commission_bps * mult,
                       min_half_spread_bps=CostModel().min_half_spread_bps * mult)
        res = run_profile(panel, dep_params, dep_sizing, cm)
        m = exposure_metrics(res, panel)
        led.log_run(reg_diag, sha, snap, {"cost_multiple": mult}, {**summary(res), **m})
        report["diagnostics"][f"cost_x{mult}"] = m
    for rate in CASH_DIAGNOSTICS:
        res = run_profile(panel, dep_params, dep_sizing, cost_model, cash_annual_rate=rate)
        m = exposure_metrics(res, panel)
        led.log_run(reg_diag, sha, snap, {"cash_annual_rate": rate}, {**summary(res), **m})
        report["diagnostics"][f"cash_{rate}"] = m

    MEMO.parent.mkdir(parents=True, exist_ok=True)
    MEMO.write_text(_memo(report))
    print(json.dumps({k: v for k, v in report.items() if k != "regime_episodes"},
                     indent=2, default=str))


def _memo(r: dict) -> str:
    ep = r["regime_episodes"]
    hits = sum(1 for e in ep if e["hit"])
    rows = "\n".join(f"| {e['start']} | {e['end']} | {e['sessions']} | "
                     f"{e['index_return_through_episode']:+.2%} | "
                     f"{e['post_episode_return']:+.2%} | {'yes' if e['hit'] else 'no'} |"
                     for e in ep)
    prof = "\n".join(
        f"| {name} | {g['summary']['cagr']:.2%} | {g['summary']['sharpe']:.2f} | "
        f"{g['summary']['max_dd']:.2%} | {g['exposure']['avg_gross']:.2f} | "
        f"{g['exposure']['return_per_unit_exposure']:.2%} | {g['exposure']['beta_vs_index']:.2f} | "
        f"{g['walk_forward']['wfe']:.2f} | {g['monkey']['profit_pctile']:.2f} | "
        f"{g['dsr']:.3f} vs {g['dsr_hurdle']:.2f} |"
        for name, g in r["profiles"].items())
    diag = "\n".join(f"| {k} | {v['cagr']:.2%} | {v['sharpe']:.2f} | {v['max_dd']:.2%} | "
                     f"{v['avg_gross']:.2f} | {v['return_per_unit_exposure']:.2%} |"
                     for k, v in r["diagnostics"].items())
    return f"""# Clenow Momentum — Calibration Memo

**Snapshot:** `{r['snapshot']}` · **Code:** `{r['code_sha']}` · **Cash rate:** {r['cash_annual_rate']:.2%}

Generated by `number7.research.calibrate_clenow`. Numbers are machine-written; the
interpretation sections below are written by hand and are the point of the document.

## Window

Published results span roughly 1999–2014; our history starts 2004. The overlap
(2005–2014, after warm-up) is the quantitative comparison; 2015→present is
post-publication validation. **The missing 2000–2003 window removes the dot-com bear** —
arguably the episode that best justifies a 200-day regime filter — leaving 2008 as the only
severe bear in sample.

## Profiles

The reference profile is **fidelity evidence only and is never deployable evidence.**

| profile | CAGR | Sharpe | max DD | avg gross | return / unit exposure | beta | WFE | monkey pctile | DSR |
|---|---|---|---|---|---|---|---|---|---|
{prof}

## Regime-off episodes ({hits}/{len(ep)} preceded a negative index move)

| start | end | sessions | index return through episode | ~3m after re-entry | hit |
|---|---|---|---|---|---|
{rows}

## Turnover

- average: {r['turnover']['avg_turnover']:.2%}
- **at regime transitions:** {r['turnover']['avg_turnover_at_transitions']:.2%} over
  {r['turnover']['n_transitions']} rebalances — whipsaw spikes are the known SMA-crossing
  failure mode and an average hides them.

## Diagnostics (excluded from the DSR trial count)

| run | CAGR | Sharpe | max DD | avg gross | return / unit exposure |
|---|---|---|---|---|---|
{diag}

## Declared platform adaptations

- **Cadence:** the published system maintains the roster weekly but re-sizes every second
  Wednesday; we rebalance weekly (Tuesday default) with MOC fills. Turnover differences
  trace to this, not to a bug.
- **Cash rate:** primary runs earn {r['cash_annual_rate']:.2%} on cash. The 2%/4%
  diagnostics above bound the handicap; the blueprint routes idle cash to a T-bill sleeve,
  which this engine does not yet model.
- **Regime proxy:** capital-adjusted SPY. `$SPX` from Norgate's US Indices database is a
  registered VARIANT, not a free swap.
- **Gap definition:** overnight (`|open / prev_close − 1|`). Norgate defines the open as the
  first print from any venue while the close is generally the listing-exchange auction, so
  vendor-specific outliers are possible.

## To be written by hand

1. Does the overlap-window comparison support fidelity? Name the specific discrepancies.
2. Paired regime-gate ablation: is (gated − ungated) positive on exposure-adjusted terms?
3. Do the ablations behave as expected, and does anything beat the full system?
4. **Delisting:** state whether the Norgate total-return series embeds a terminal delisting
   return. If it does not, the backtest overstates. Event count this run:
   see `delisting_exits` in the profile table source.
5. **Index membership:** confirm from Norgate documentation that membership intervals are
   EFFECTIVE dates, not announcement dates. Announcement dates would make the book trade
   the S&P-addition pop — a real look-ahead. Deletion-date exits are the classic
   worst-execution point and are a recorded known cost.
6. Verdict: proceed to paper, or documented kill.
"""


if __name__ == "__main__":
    main()
