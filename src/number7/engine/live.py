from __future__ import annotations

from pathlib import Path

import pandas as pd

from number7.data.snapshot import SnapshotPaths, read_meta
from number7.data.store import load_price_panel
from number7.data.universe import in_index_flags, load_membership
from number7.engine.schedule import signal_date
from number7.engine.strategy import PanelView, Strategy, mask_unquoted, validate_weights
from number7.strategies.sizing import SizingConfig, resolve_book

REQUIRED_BASES = ("totalreturn", "capital")


class MissingBasisError(RuntimeError):
    """The snapshot predates the dual-basis schema, so signals would be computed on the
    total-return basis and systematically tilted toward high-dividend names (spec §2)."""


def build_panel(snapshot_root: Path, start: str | None = None) -> PanelView:
    paths = SnapshotPaths(snapshot_root)
    meta = read_meta(paths)
    missing = [b for b in REQUIRED_BASES if b not in meta.bases]
    if missing:
        raise MissingBasisError(
            f"snapshot {snapshot_root.name} records bases {meta.bases}; missing {missing}. "
            "Re-sync with the dual-basis pull before running any signal code.")
    tidy = load_price_panel(snapshot_root, start=start)

    def piv(col: str) -> pd.DataFrame:
        return tidy.pivot(index="date", columns="symbol", values=col).sort_index()

    px_close = piv("px_close")
    membership = load_membership(snapshot_root)
    # in_index means ACTUAL point-in-time index membership. Extras (SPY) are deliberately
    # NOT flagged: the regime instrument must not be a buyable candidate, and must not
    # inflate the hold_top_pct denominator (spec §6.2, confirmed defect #1).
    flags = in_index_flags(membership, list(px_close.columns), px_close.index)
    meta_df = pd.read_parquet(paths.metadata).set_index("symbol")
    assetid = pd.to_numeric(meta_df["assetid"], errors="coerce") \
                .reindex(px_close.columns).astype(float)
    if "gics_sector" not in meta_df.columns:
        raise ValueError(
            f"snapshot {snapshot_root.name} metadata has no gics_sector column - schema "
            "regression; the risk layer's sector cap cannot run (risk spec §4.6)")
    gics = meta_df["gics_sector"].reindex(px_close.columns)
    return PanelView(px_open=piv("px_open"), px_high=piv("px_high"), px_low=piv("px_low"),
                     px_close=px_close, tr_close=piv("tr_close"), raw_close=piv("raw_close"),
                     volume=piv("volume"), in_index=flags, assetid=assetid,
                     gics_sector=gics)


def compute_live_targets(strategy: Strategy, panel: PanelView, asof: pd.Timestamp, *,
                         current: pd.Series | None = None,
                         sizing: SizingConfig | None = None,
                         stale_periods: pd.Series | None = None) -> pd.Series:
    """THE Phase-2 order-service entry point: weights to execute at `asof`'s close,
    decided strictly from data <= the prior session (blueprint §4.1 timing contract).

    `current` MUST be built with holdings_from_shares() from broker share counts and the
    signal date's official close (spec §8.4), and MUST reflect a healthy broker snapshot —
    stale or degraded broker truth degrades to hold-state / no trades, never to treating an
    unknown position as flat. It is therefore REQUIRED whenever `sizing` is supplied: an
    omitted `current` cannot be distinguished from a genuinely flat book, and under
    regime-off `resolve_book` restricts admission to names with `current > 0`, so defaulting
    it to zeros would liquidate the entire sleeve. A caller that really is flat passes an
    explicit all-zero Series and says so."""
    cols = panel.px_close.columns
    sig = signal_date(panel.sessions, asof)
    view = panel.masked_to(sig)
    slate = strategy.target_weights(view)
    tradeable = mask_unquoted(slate, panel, sig, cols)
    if sizing is None:
        return validate_weights(tradeable.weights, name=strategy.manifest.name)
    if current is None:
        raise ValueError(
            "compute_live_targets requires `current` when `sizing` is supplied: an unknown "
            "book must not be treated as flat (spec §8.4). Pass holdings_from_shares(...), "
            "or an explicit all-zero Series if the sleeve genuinely holds nothing.")
    cur = current.reindex(cols).fillna(0.0)
    return resolve_book(tradeable, cur, sizing, stale_periods).reindex(cols).fillna(0.0)
