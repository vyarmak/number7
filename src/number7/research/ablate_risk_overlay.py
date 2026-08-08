"""Risk-overlay ablation runner (risk spec §9). Run:

    uv run python -m number7.research.ablate_risk_overlay

Two cells only - the deployable Clenow profile with and without the overlay, same
snapshot, both logged to the ledger under DIAGNOSTIC_FAMILY (zero searched dimensions;
the run measures the overlay's cost/benefit and cannot change any shipped value).

Report criteria (risk spec §9): monkey drawdown percentile on the overlay-on book,
realized post-k vol vs the 10% target PATH (the ratchet bounds k, not delivered vol),
CAGR/Sharpe cost, cap bind rates by stage with sector binds split at the 2016-08-31 and
2018-09-28 GICS boundaries and top3-without-sector binds separated, the applied_k path
through 2008/2020/2022, and an explicit note that ADV no-binds at $50k are expected and
are NOT evidence the mechanism works."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from number7.config import get_settings
from number7.data.snapshot import current_snapshot
from number7.engine.backtest import BacktestResult, run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.live import build_panel
from number7.engine.schedule import weekly_rebalances
from number7.research.calibrate_clenow import (PROFILES, SLEEVE_EQUITY, _code_sha,
                                               _n_obs)
from number7.research.ledger import Ledger
from number7.research.preregs import RISK_OVERLAY_ABLATION
from number7.risk.overlay import RiskConfig
from number7.strategies.clenow import ClenowMomentum
from number7.validation.monkey import monkey_test

MEMO_PATH = "docs/research/2026-08-risk-overlay-ablation.md"
GICS_BOUNDARIES = (pd.Timestamp("2016-08-31"), pd.Timestamp("2018-09-28"))
STRESS_WINDOWS = {"2008": ("2008-01-01", "2009-06-30"),
                  "2020": ("2020-01-01", "2020-12-31"),
                  "2022": ("2022-01-01", "2022-12-31")}


def realized_vol_path(result: BacktestResult, window: int = 63) -> pd.Series:
    """Rolling annualized vol of the equity curve - the DELIVERED risk, which the
    ratchet does not bound (it bounds k; turnover can move w'Σw under a bounded k)."""
    r = np.log(result.equity.dropna()).diff().dropna()
    return r.rolling(window).std(ddof=0) * np.sqrt(252.0)


def bind_rates(result: BacktestResult) -> dict:
    """Cap bind rates from the recorded per-rebalance diagnostics, sector split at the
    GICS reshuffle boundaries (risk spec §4.6 - the PIT approximation must be VISIBLE),
    and top3-without-sector separated (the two caps overlap on a concentrated book)."""
    diag = result.risk_diag or {}
    if not diag:
        return {"n": 0}
    dates = sorted(diag)
    b16, b18 = GICS_BOUNDARIES

    def _rate(sel) -> float:
        hits = [t for t in dates if sel(t)]
        if not hits:
            return float("nan")
        return float(np.mean([bool(diag[t]["sector_bound"]) for t in hits]))

    top3_alone = [t for t in dates
                  if diag[t]["top3_bound"] and not diag[t]["sector_bound"]]
    return {
        "n": len(dates),
        "sector_bind_rate_pre2016": _rate(lambda t: t < b16),
        "sector_bind_rate_2016_2018": _rate(lambda t: b16 <= t < b18),
        "sector_bind_rate_post2018": _rate(lambda t: t >= b18),
        "top3_bind_rate": float(np.mean([diag[t]["top3_bound"] for t in dates])),
        "top3_without_sector_rate": len(top3_alone) / len(dates),
        "adv_bind_rate": float(np.mean([bool(diag[t]["adv_bound"]) for t in dates])),
    }


def applied_k_stress_paths(result: BacktestResult) -> dict:
    ks = result.risk_k if result.risk_k is not None else pd.Series(dtype=float)
    out = {}
    for label, (a, b) in STRESS_WINDOWS.items():
        seg = ks.loc[a:b]
        out[label] = {"n": int(len(seg)),
                      "min": float(seg.min()) if len(seg) else float("nan"),
                      "mean": float(seg.mean()) if len(seg) else float("nan")}
    return out


def _report(on: BacktestResult, off: BacktestResult, *, monkey: dict | None,
            snapshot: str, code_sha: str) -> str:
    s_on, s_off = summary(on), summary(off)
    rv = realized_vol_path(on).dropna()
    lines = [
        "# Risk Overlay — Ablation Report",
        "",
        f"Snapshot `{snapshot}`, code `{code_sha}`. Pre-registered two-cell diagnostic",
        "(RISK_OVERLAY_ABLATION): overlay-on vs overlay-off on the deployable profile.",
        "Frozen parameters throughout — this report cannot change any shipped value.",
        "",
        "## Headline cost/benefit",
        "",
        "| metric | overlay ON | overlay OFF |",
        "|---|---|---|",
    ]
    for key in ("cagr", "sharpe", "max_dd", "avg_turnover"):
        lines.append(f"| {key} | {s_on[key]:.4f} | {s_off[key]:.4f} |")
    lines += [
        "",
        "## Monkey drawdown",
        "",
        (f"Overlay-on matched-null result: {json.dumps(monkey, default=str)}"
         if monkey is not None else "Monkey test not run (fast mode)."),
        "",
        "## Realized vol vs target",
        "",
        f"Post-k realized vol (rolling 63d, annualized): mean {rv.mean():.4f}, "
        f"p95 {rv.quantile(0.95):.4f} against the 0.10 target. The ratchet bounds k, "
        "not delivered vol — this path is the overlay's actual output.",
        "",
        "## Cap bind rates",
        "",
        f"`{json.dumps(bind_rates(on), default=str)}`",
        "",
        "Sector rates are split at the 2016/2018 GICS boundaries because the sector map",
        "is a declared PIT approximation (risk spec §4.6); pre-2016 rates are measured",
        "against labels the live system would not have had.",
        "",
        "ADV no-binds at $50k are expected and are NOT evidence the mechanism works —",
        "the cap is forward-looking fail-closed protection, inert at this equity.",
        "",
        "## applied_k path",
        "",
        f"`{json.dumps(applied_k_stress_paths(on), default=str)}`",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    settings = get_settings()
    root = current_snapshot(settings)
    if root is None:
        raise SystemExit("no promoted snapshot: run number7.ops.nightly first")
    panel = build_panel(root)
    cost_model = CostModel()
    led = Ledger(settings.data_dir / "trials.duckdb")
    sha, snap = _code_sha(), root.name
    reg = led.register_once(RISK_OVERLAY_ABLATION)

    params, sizing = PROFILES["deployable"]
    rb = weekly_rebalances(panel.sessions)
    on = run_backtest(ClenowMomentum(params), panel, rb, cost_model, sizing=sizing,
                      initial=SLEEVE_EQUITY, risk_cfg=RiskConfig())
    off = run_backtest(ClenowMomentum(params), panel, rb, cost_model, sizing=sizing,
                       initial=SLEEVE_EQUITY)
    mk = monkey_test(on, panel, rb, cost_model,
                     null_factory=lambda s: ClenowMomentum(params, shuffle_seed=s),
                     sizing=sizing, initial=SLEEVE_EQUITY, n_monkeys=1000, seed=17,
                     risk_cfg=RiskConfig())

    for label, res in (("on", on), ("off", off)):
        led.log_run(reg, sha, snap, {"overlay": label},
                    {**summary(res), "n_obs": _n_obs(res)})

    from pathlib import Path
    memo = Path(MEMO_PATH)
    memo.parent.mkdir(parents=True, exist_ok=True)
    memo.write_text(_report(on, off, monkey=mk, snapshot=snap, code_sha=sha))
    print(json.dumps({"on": summary(on), "off": summary(off), "monkey": mk},
                     indent=2, default=str))


if __name__ == "__main__":
    main()
