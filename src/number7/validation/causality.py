from __future__ import annotations

from typing import Callable

import pandas as pd

from number7.engine.live import compute_live_targets
from number7.engine.strategy import PanelView, Strategy


def causality_violations(strategy_from_panel: Callable[[PanelView], Strategy],
                         panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                         truncate_last_n: int = 5) -> list[pd.Timestamp]:
    """Truncate-and-compare (Chan, KB-07): a causal strategy's decided weights on the
    overlap must be identical whether or not the future tail of the data exists.

    `strategy_from_panel` builds a FRESH strategy from the panel the harness supplies —
    any data the strategy precomputes must come from that panel, so truncation reaches
    everything the strategy could have leaked from.
    """
    if not 0 < truncate_last_n < len(panel.close.index):
        raise ValueError(f"truncate_last_n={truncate_last_n} must be in "
                         f"[1, {len(panel.close.index) - 1}] for this panel")
    cut = panel.close.index[-(truncate_last_n + 1)]
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
