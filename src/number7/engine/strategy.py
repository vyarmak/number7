from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Protocol

import numpy as np
import pandas as pd
from pydantic import BaseModel


@dataclass(frozen=True)
class PanelView:
    """Dual-basis point-in-time panel (spec §7). Basis assignment is normative:
    px_* (capital-adjusted) for every SIGNAL computation, tr_close for P&L and
    benchmarks, raw_close for fills, ADV and broker reconciliation. There is no
    field called `close` on purpose — every reader must name its basis."""

    px_open: pd.DataFrame
    px_high: pd.DataFrame
    px_low: pd.DataFrame
    px_close: pd.DataFrame
    tr_close: pd.DataFrame
    raw_close: pd.DataFrame
    volume: pd.DataFrame
    in_index: pd.DataFrame
    assetid: pd.Series          # symbol -> Norgate assetid; stable tie-break key (§6.1)

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return self.px_close.index

    @property
    def view_end(self) -> pd.Timestamp:
        return self.px_close.index[-1]

    def masked_to(self, end: pd.Timestamp) -> "PanelView":
        return PanelView(
            px_open=self.px_open.loc[:end], px_high=self.px_high.loc[:end],
            px_low=self.px_low.loc[:end], px_close=self.px_close.loc[:end],
            tr_close=self.tr_close.loc[:end], raw_close=self.raw_close.loc[:end],
            volume=self.volume.loc[:end], in_index=self.in_index.loc[:end],
            assetid=self.assetid,          # not time-indexed: nothing to truncate
        )


class StrategyManifest(BaseModel):
    name: str
    family: str
    origin: Literal["human", "llm"]
    params: dict
    reentry_blackout_days: int = 0


@dataclass(frozen=True)
class Slate:
    """What a strategy emits (spec §5.2). ABSOLUTE, unbudgeted weights for every ELIGIBLE
    name plus the rank vector over the full point-in-time constituent set, so the
    holdings-aware resolver can reconstruct the budget-constrained fill. Never normalized
    to sum 1 — normalizing would cancel risk_factor and destroy the emergent position count."""

    weights: pd.Series      # absolute ATR-parity weight for ALL eligible names
    rank: pd.Series         # 1-based raw rank over constituents; NaN where unrankable
    admit_new: bool         # the regime gate: allow_open_new_symbols


def full_slate(weights: pd.Series) -> Slate:
    """Slate for an always-invested strategy (benchmarks, null fixtures): rank follows
    descending weight, unfunded names are unranked."""
    funded = weights[weights > 0].sort_values(ascending=False, kind="mergesort")
    rank = pd.Series(np.nan, index=weights.index, dtype=float)
    rank[funded.index] = np.arange(1.0, len(funded) + 1.0)
    return Slate(weights=weights, rank=rank, admit_new=True)


def mask_unquoted(slate: Slate, panel: PanelView, sig: pd.Timestamp, cols) -> Slate:
    """Force weight to 0 for any symbol with no quote at the signal date `sig` (spec §8.4).

    A held name can go dark without the strategy noticing - it keeps re-emitting its old
    weight, and a naive resolver would then retain or even enter a position with no price
    to size a trade against. Called identically by run_backtest and compute_live_targets so
    a delisting is handled the same way on both paths (golden replay must not pass on a
    fixture while the live path silently diverges on a name that has gone dark)."""
    no_quote = panel.tr_close.loc[sig].reindex(cols).isna()
    weights = slate.weights.reindex(cols).fillna(0.0).where(~no_quote, 0.0)
    return replace(slate, weights=weights)


class Strategy(Protocol):
    manifest: StrategyManifest

    def target_weights(self, view: PanelView) -> Slate: ...


def validate_weights(w: pd.Series, name: str = "strategy") -> pd.Series:
    """Enforce the Phase-1 long-only, unlevered contract (blueprint §8): weights finite,
    >= 0, sum <= 1 (cash is the remainder). The engine's drift/cash math relies on this."""
    if not np.isfinite(w.to_numpy(dtype=float)).all():
        bad = list(w.index[~np.isfinite(w.astype(float))])[:3]
        raise ValueError(f"{name} emitted non-finite weights: {bad}")
    if (w < -1e-12).any():
        bad = list(w.index[w < -1e-12])[:3]
        raise ValueError(f"{name} emitted negative weights (shorting not supported): {bad}")
    total = float(w.sum())
    if total > 1.0 + 1e-9:
        raise ValueError(f"{name} emitted gross weight {total:.4f} > 1.0 (leverage not supported)")
    return w


class RandomTopN:
    """Null strategy: random ranking, equal-weight top n members. Calibration fixture."""

    def __init__(self, n: int, seed: int) -> None:
        self.manifest = StrategyManifest(name=f"random_top{n}", family="null",
                                         origin="human", params={"n": n, "seed": seed})
        self._rng = np.random.default_rng(seed)
        self.n = n

    def target_weights(self, view: PanelView) -> Slate:
        members = view.in_index.iloc[-1]
        candidates = list(members.index[members])
        picks = list(self._rng.permutation(candidates))[: self.n]
        w = pd.Series(0.0, index=view.px_close.columns)
        if picks:
            w[picks] = 1.0 / len(picks)   # fully allocate even when universe < n
        return full_slate(w)


class LookaheadTrap:
    """DELIBERATELY CHEATS: ranks by the return from `t` to the END of its stored data
    (an end-of-data leak — the classic vectorized-precompute bug). Harness-test fixture:
    built from a panel, so truncate-and-compare changes what it can see."""

    def __init__(self, n: int, full_close: pd.DataFrame) -> None:
        self.manifest = StrategyManifest(name="lookahead_trap", family="trap",
                                         origin="human", params={"n": n})
        self.n, self._full_close = n, full_close

    def target_weights(self, view: PanelView) -> Slate:
        t = view.view_end
        w = pd.Series(0.0, index=view.px_close.columns)
        if self._full_close.index[-1] <= t:
            return full_slate(w)
        leak = np.log(self._full_close.iloc[-1] / view.px_close.loc[t]).fillna(-np.inf)
        picks = leak.nlargest(self.n).index
        w[picks] = 1.0 / self.n
        return full_slate(w)
