"""Corwin-Schultz high-low spread estimator and the risk-layer entry gate (spec §5).

CS output is a DIMENSIONLESS relative spread (already price-normalized). It is a
continuous-market proxy used as a conservative admission heuristic - it is NOT an
estimate of MOC-auction execution cost and its level must not be read as a forecast."""

from __future__ import annotations

import numpy as np
import pandas as pd

_K = 3.0 - 2.0 * np.sqrt(2.0)


def corwin_schultz(px_high: pd.DataFrame, px_low: pd.DataFrame) -> pd.DataFrame:
    hl = np.log(px_high / px_low)
    beta = hl ** 2 + (hl ** 2).shift(1)
    h2 = np.maximum(px_high, px_high.shift(1))
    l2 = np.minimum(px_low, px_low.shift(1))
    gamma = np.log(h2 / l2) ** 2
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / _K - np.sqrt(gamma / _K)
    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    return spread.clip(lower=0.0)


def spread_gate_frame(px_high: pd.DataFrame, px_low: pd.DataFrame, *,
                      est_window: int = 21, base_window: int = 252,
                      spread_mult: float = 2.0,
                      spread_floor: float = 0.0010) -> pd.DataFrame:
    """The gate decision for EVERY row: .loc[d] equals spread_gate on data truncated
    at d, because every input is backward-looking (shift/rolling). The engine
    precomputes this once per run instead of recomputing the rolling medians per
    rebalance - the dominant cost of an overlay backtest."""
    stat = corwin_schultz(px_high, px_low) \
        .rolling(est_window, min_periods=est_window).median()
    base = stat.shift(est_window).rolling(base_window, min_periods=base_window).median()
    threshold = np.maximum(spread_mult * base, spread_floor)
    return (stat > threshold) & base.notna() & stat.notna()


def spread_gate(px_high: pd.DataFrame, px_low: pd.DataFrame, *, est_window: int = 21,
                base_window: int = 252, spread_mult: float = 2.0,
                spread_floor: float = 0.0010) -> pd.Series:
    """True = block NEW entry at the last row. The baseline is the rolling median of the
    est_window-session statistic over base_window sessions ENDING est_window sessions
    before the signal date - the baseline must not contain the episode it is judging
    (spec §5). Names with insufficient baseline history are never blocked here (the
    min_obs bar and eligibility filters own that case)."""
    return spread_gate_frame(px_high, px_low, est_window=est_window,
                             base_window=base_window, spread_mult=spread_mult,
                             spread_floor=spread_floor).iloc[-1]
