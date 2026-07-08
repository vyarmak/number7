from __future__ import annotations

from pathlib import Path

import pandas as pd

from number7.data.store import load_price_panel
from number7.data.universe import in_index_flags, load_membership
from number7.engine.schedule import signal_date
from number7.engine.strategy import PanelView, Strategy, validate_weights


def build_panel(snapshot_root: Path, start: str | None = None) -> PanelView:
    tidy = load_price_panel(snapshot_root, start=start)

    def piv(col: str) -> pd.DataFrame:
        return tidy.pivot(index="date", columns="symbol", values=col).sort_index()

    close = piv("close")
    membership = load_membership(snapshot_root)
    flags = in_index_flags(membership, list(close.columns), close.index)
    extra = set(close.columns) - set(membership["symbol"])   # e.g. SPY: always tradable
    flags.loc[:, sorted(extra)] = True
    return PanelView(close=close, volume=piv("volume"),
                     unadjusted_close=piv("unadjusted_close"), in_index=flags)


def compute_live_targets(strategy: Strategy, panel: PanelView, asof: pd.Timestamp) -> pd.Series:
    """THE Phase-2 order-service entry point: weights to execute at `asof`'s close,
    decided strictly from data <= the prior session (blueprint §4.1 timing contract)."""
    view = panel.masked_to(signal_date(panel.close.index, asof))
    return validate_weights(
        strategy.target_weights(view).reindex(panel.close.columns).fillna(0.0),
        name=strategy.manifest.name)
