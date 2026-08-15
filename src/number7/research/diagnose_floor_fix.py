"""Floor-fix diagnostic runner (amendment 1, spec 2026-08-14). Run:

    uv run python -m number7.research.diagnose_floor_fix

Two cells on the AMENDED pipeline (structural floor): tv=0.10 with 1000 matched
monkeys (the acceptance cell - monkey profit percentile is the criterion), and
tv=0.12 cell-only as RESEARCH input for the 6-month live-gate memo. Controls are the
RISK_OVERLAY_ABLATION ledger rows (old floor, same code lineage). Report-only."""

from __future__ import annotations

import json
from pathlib import Path

from number7.config import get_settings
from number7.data.snapshot import current_snapshot
from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.live import build_panel
from number7.engine.schedule import weekly_rebalances
from number7.research.ablate_risk_overlay import (applied_k_stress_paths, bind_rates,
                                                  realized_vol_path)
from number7.research.calibrate_clenow import (PROFILES, SLEEVE_EQUITY, _code_sha,
                                               _n_obs)
from number7.research.ledger import Ledger
from number7.research.preregs import FLOOR_FIX_DIAGNOSTIC
from number7.risk.overlay import RiskConfig
from number7.strategies.clenow import ClenowMomentum
from number7.validation.monkey import monkey_test

MEMO_PATH = "docs/research/2026-08-floor-fix-diagnostic.md"


def _gross(res) -> float:
    return float(res.weights.sum(axis=1).mean()) if len(res.weights) else 0.0


def main() -> None:
    settings = get_settings()
    root = current_snapshot(settings)
    if root is None:
        raise SystemExit("no promoted snapshot: run number7.ops.nightly first")
    panel = build_panel(root)
    cost_model = CostModel()
    led = Ledger(settings.data_dir / "trials.duckdb")
    sha, snap = _code_sha(), root.name
    reg = led.register_once(FLOOR_FIX_DIAGNOSTIC)

    params, sizing = PROFILES["deployable"]
    rb = weekly_rebalances(panel.sessions)
    cells = {}
    for tv in (0.10, 0.12):
        cells[tv] = run_backtest(ClenowMomentum(params), panel, rb, cost_model,
                                 sizing=sizing, initial=SLEEVE_EQUITY,
                                 risk_cfg=RiskConfig(target_vol=tv))
    mk = monkey_test(cells[0.10], panel, rb, cost_model,
                     null_factory=lambda s: ClenowMomentum(params, shuffle_seed=s),
                     sizing=sizing, initial=SLEEVE_EQUITY, n_monkeys=1000, seed=17,
                     risk_cfg=RiskConfig(target_vol=0.10))

    for tv, res in cells.items():
        led.log_run(reg, sha, snap, {"floor": "structural", "target_vol": tv},
                    {**summary(res), "n_obs": _n_obs(res)})

    rv10 = realized_vol_path(cells[0.10]).dropna()
    lines = [
        "# Floor Fix Diagnostic — Amendment 1 Validation",
        "",
        f"Snapshot `{snap}`, code `{sha}`. Pre-registered FLOOR_FIX_DIAGNOSTIC: the",
        "AMENDED pipeline (structural $1000 floor). Controls: RISK_OVERLAY_ABLATION",
        "rows (old post-scalar floor). The tv=0.12 cell is research for the live-gate",
        "memo only.",
        "",
        "## Cells",
        "",
        "| metric | structural floor, tv=0.10 | structural floor, tv=0.12 (research) |",
        "|---|---|---|",
    ]
    s10, s12 = summary(cells[0.10]), summary(cells[0.12])
    for key in ("cagr", "sharpe", "max_dd", "avg_turnover"):
        lines.append(f"| {key} | {s10[key]:.4f} | {s12[key]:.4f} |")
    lines += [
        f"| avg gross | {_gross(cells[0.10]):.4f} | {_gross(cells[0.12]):.4f} |",
        "",
        "Old-floor controls (ablation, same snapshot lineage): overlay-on CAGR 0.0340,",
        "Sharpe 0.3937, max_dd -0.1633, avg gross 0.4452; monkey profit percentile",
        "0.491, dd percentile 0.339.",
        "",
        "## Acceptance cell monkeys (tv=0.10, 1000 matched, overlay-inheriting)",
        "",
        f"`{json.dumps(mk, default=str)}`",
        "",
        "## Realized vol vs target (tv=0.10 cell)",
        "",
        f"Rolling 63d annualized: mean {rv10.mean():.4f}, p95 {rv10.quantile(0.95):.4f}"
        " against the 0.10 target.",
        "",
        "## Bind rates and applied_k stress paths (tv=0.10 cell)",
        "",
        f"`{json.dumps(bind_rates(cells[0.10]), default=str)}`",
        "",
        f"`{json.dumps(applied_k_stress_paths(cells[0.10]), default=str)}`",
        "",
    ]
    memo = Path(MEMO_PATH)
    memo.parent.mkdir(parents=True, exist_ok=True)
    memo.write_text("\n".join(lines))
    print(json.dumps({"tv010": s10, "tv012": s12, "monkey": mk}, indent=2,
                     default=str))


if __name__ == "__main__":
    main()
