from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
import pandas as pd
from pydantic import BaseModel


@dataclass(frozen=True)
class PanelView:
    close: pd.DataFrame
    volume: pd.DataFrame
    unadjusted_close: pd.DataFrame
    in_index: pd.DataFrame

    @property
    def view_end(self) -> pd.Timestamp:
        return self.close.index[-1]

    def masked_to(self, end: pd.Timestamp) -> "PanelView":
        return PanelView(*(df.loc[:end] for df in
                           (self.close, self.volume, self.unadjusted_close, self.in_index)))


class StrategyManifest(BaseModel):
    name: str
    family: str
    origin: Literal["human", "llm"]
    params: dict
    reentry_blackout_days: int = 0


class Strategy(Protocol):
    manifest: StrategyManifest

    def target_weights(self, view: PanelView) -> pd.Series: ...


def validate_weights(w: pd.Series, name: str = "strategy") -> pd.Series:
    """Enforce the Phase-1 long-only, unlevered contract (blueprint §8): weights >= 0,
    sum <= 1 (cash is the remainder). The engine's drift/cash math relies on this."""
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

    def target_weights(self, view: PanelView) -> pd.Series:
        members = view.in_index.iloc[-1]
        candidates = list(members.index[members])
        picks = list(self._rng.permutation(candidates))[: self.n]
        w = pd.Series(0.0, index=view.close.columns)
        if picks:
            w[picks] = 1.0 / len(picks)   # fully allocate even when universe < n
        return w


class LookaheadTrap:
    """DELIBERATELY CHEATS: ranks by the return from `t` to the END of its stored data
    (an end-of-data leak — the classic vectorized-precompute bug). Harness-test fixture:
    built from a panel, so truncate-and-compare changes what it can see."""

    def __init__(self, n: int, full_close: pd.DataFrame) -> None:
        self.manifest = StrategyManifest(name="lookahead_trap", family="trap",
                                         origin="human", params={"n": n})
        self.n, self._full_close = n, full_close

    def target_weights(self, view: PanelView) -> pd.Series:
        t = view.view_end
        w = pd.Series(0.0, index=view.close.columns)
        if self._full_close.index[-1] <= t:
            return w
        leak = np.log(self._full_close.iloc[-1] / view.close.loc[t]).fillna(-np.inf)
        picks = leak.nlargest(self.n).index
        w[picks] = 1.0 / self.n
        return w
