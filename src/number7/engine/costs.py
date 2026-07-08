from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

_DEN = 3 - 2 * np.sqrt(2.0)


def corwin_schultz(high: pd.Series, low: pd.Series, window: int = 21) -> pd.Series:
    """Corwin-Schultz (2012) 2-day high-low spread estimator, rolling-averaged."""
    with np.errstate(divide="ignore", invalid="ignore"):
        hl = np.log(high / low) ** 2
        beta = hl + hl.shift(-1)
        h2 = pd.concat([high, high.shift(-1)], axis=1).max(axis=1)
        l2 = pd.concat([low, low.shift(-1)], axis=1).min(axis=1)
        gamma = np.log(h2 / l2) ** 2
        alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / _DEN - np.sqrt(gamma / _DEN)
        s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return s.clip(lower=0).rolling(window, min_periods=5).mean()


def impact_cost(q_over_adv: float, daily_sigma: float) -> float:
    return (2.0 / 3.0) * daily_sigma * float(np.sqrt(max(q_over_adv, 0.0)))


class CostModel(BaseModel):
    commission_bps: float = 0.0
    min_half_spread_bps: float = 2.0

    def one_way_cost(self, spread_est: float, q_over_adv: float, sigma: float) -> float:
        half_spread = max(spread_est / 2.0, self.min_half_spread_bps / 1e4)
        return self.commission_bps / 1e4 + half_spread + impact_cost(q_over_adv, sigma)
