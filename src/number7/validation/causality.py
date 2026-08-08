from __future__ import annotations

from typing import Callable

import pandas as pd

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.live import compute_live_targets
from number7.engine.strategy import PanelView, Strategy
from number7.strategies.sizing import SizingConfig


def causality_violations(strategy_from_panel: Callable[[PanelView], Strategy],
                         panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                         truncate_last_n: int = 5) -> list[pd.Timestamp]:
    """Truncate-and-compare (Chan, KB-07): a causal strategy's decided weights on the
    overlap must be identical whether or not the future tail of the data exists.

    `strategy_from_panel` builds a FRESH strategy from the panel the harness supplies —
    any data the strategy precomputes must come from that panel, so truncation reaches
    everything the strategy could have leaked from.
    """
    if not 0 < truncate_last_n < len(panel.sessions):
        raise ValueError(f"truncate_last_n={truncate_last_n} must be in "
                         f"[1, {len(panel.sessions) - 1}] for this panel")
    cut = panel.sessions[-(truncate_last_n + 1)]
    truncated = panel.masked_to(cut)
    common = [t for t in rebalance_dates if t <= cut]
    full_s, trunc_s = strategy_from_panel(panel), strategy_from_panel(truncated)
    bad: list[pd.Timestamp] = []
    for t in common:
        w_full = compute_live_targets(full_s, panel, asof=t)
        w_trunc = compute_live_targets(trunc_s, truncated, asof=t) \
            .reindex(w_full.index).fillna(0.0)
        if not w_full.round(12).equals(w_trunc.round(12)):
            bad.append(t)
    return bad


def closed_loop_violations(strategy_from_panel: Callable[[PanelView], Strategy],
                           panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                           cost_model: CostModel, *, sizing: SizingConfig | None = None,
                           risk_cfg=None, truncate_last_n: int = 5) -> list[str]:
    """Trajectory-level truncate-and-compare (spec §10.3). causality_violations() proves
    panel purity at ONE holdings point; a path-dependent, part-cash strategy also has to
    reach the same STATE. Runs the full and truncated simulations from the same initial
    state and compares every overlapping slate, resolved book and transition."""
    sessions = panel.sessions
    if not 0 < truncate_last_n < len(sessions):
        raise ValueError(f"truncate_last_n={truncate_last_n} must be in "
                         f"[1, {len(sessions) - 1}] for this panel")
    cut = sessions[-(truncate_last_n + 1)]
    truncated = panel.masked_to(cut)
    common = pd.DatetimeIndex([t for t in rebalance_dates if t <= cut])
    kw = dict(cost_model=cost_model, sizing=sizing, record_slates=True,
              risk_cfg=risk_cfg)
    full = run_backtest(strategy_from_panel(panel), panel, common, **kw)
    trunc = run_backtest(strategy_from_panel(truncated), truncated, common, **kw)

    bad: list[str] = []
    for t in common:
        if t not in full.slates or t not in trunc.slates:
            bad.append(f"{t.date()}: rebalance executed in only one run")
            continue
        a, b = full.slates[t], trunc.slates[t]
        cols = b.weights.index
        if a.admit_new != b.admit_new:
            bad.append(f"{t.date()}: admit_new {a.admit_new} != {b.admit_new}")
        if not a.weights[cols].round(12).equals(b.weights.round(12)):
            bad.append(f"{t.date()}: slate weights differ")
        if not a.rank[cols].round(12).equals(b.rank.round(12)):
            bad.append(f"{t.date()}: slate rank differs")
        for label, fa, fb in (("state_at_signal", full.state_at_signal, trunc.state_at_signal),
                              ("resolved_book", full.weights, trunc.weights)):
            if not fa.loc[t, cols].round(12).equals(fb.loc[t].round(12)):
                bad.append(f"{t.date()}: {label} differs")
    if not full.equity.loc[:cut].round(12).equals(trunc.equity.loc[:cut].round(12)):
        bad.append(f"equity trajectory differs on the overlap through {cut.date()}")
    return bad
