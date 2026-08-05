from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from number7.engine.backtest import BacktestResult, run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, RandomTopN, Strategy
from number7.strategies.sizing import SizingConfig


def _avg_gross(res: BacktestResult) -> float:
    return float(res.weights.sum(axis=1).mean()) if len(res.weights) else 0.0


def monkey_test(candidate: BacktestResult, panel: PanelView,
                rebalance_dates: pd.DatetimeIndex, cost_model: CostModel, *,
                null_factory: Callable[[int], Strategy] | None = None,
                sizing: SizingConfig | None = None, initial: float = 1.0,
                cash_annual_rate: float = 0.0,
                n_monkeys: int = 1000, seed: int = 0) -> dict:
    """Davey's monkey test (KB-07): random systems matched on the candidate's breadth,
    identical schedule/sizing/costs (holding-period-preserving by construction — same
    weekly cadence, no IID shuffling). Production config uses n_monkeys=8000.

    `null_factory(seed) -> Strategy` supplies a MATCHED null. The default RandomTopN is
    always fully invested and equal-weight, which is a mismatched null for a part-cash,
    ATR-sized candidate — it measures cash exposure rather than ranking skill (spec §10.2).
    A Clenow run must pass `lambda s: ClenowMomentum(params, shuffle_seed=s)`, which
    randomizes only the RANKING and keeps the filters, regime gate, sizing and resolution
    identical, plus the same `sizing` config the candidate used."""
    held = (candidate.weights > 0).sum(axis=1)
    breadth = max(int(held.median()) if len(held) else 1, 1)
    factory = null_factory or (lambda s: RandomTopN(n=breadth, seed=s))
    cand = summary(candidate)
    profits, dds, gross = [], [], []
    for k in range(n_monkeys):
        res = run_backtest(factory(seed * 100_003 + k), panel, rebalance_dates, cost_model,
                           sizing=sizing, initial=initial,
                           cash_annual_rate=cash_annual_rate)
        s = summary(res)
        profits.append(s["cagr"])
        dds.append(s["max_dd"])
        gross.append(_avg_gross(res))
    profit_pctile = float(np.mean([cand["cagr"] > p for p in profits]))
    dd_pctile = float(np.mean([cand["max_dd"] >= d for d in dds]))   # higher = shallower
    return {"profit_pctile": profit_pctile, "dd_pctile": dd_pctile,
            "beats_90": profit_pctile >= 0.9 and dd_pctile >= 0.5,
            "avg_gross_candidate": _avg_gross(candidate),
            "avg_gross_monkeys": float(np.mean(gross)) if gross else 0.0}
