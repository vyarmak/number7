from __future__ import annotations

import numpy as np
import pandas as pd

from number7.engine.backtest import BacktestResult, run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, RandomTopN


def monkey_test(candidate: BacktestResult, panel: PanelView,
                rebalance_dates: pd.DatetimeIndex, cost_model: CostModel,
                n_monkeys: int = 1000, seed: int = 0) -> dict:
    """Davey's monkey test (KB-07): random systems matched on the candidate's breadth,
    identical schedule/sizing/costs (holding-period-preserving by construction — same
    weekly cadence, no IID shuffling). Production config uses n_monkeys=8000."""
    held = (candidate.weights > 0).sum(axis=1)
    breadth = max(int(held.median()) if len(held) else 1, 1)
    cand = summary(candidate)
    profits, dds = [], []
    for k in range(n_monkeys):
        res = run_backtest(RandomTopN(n=breadth, seed=seed * 100_003 + k),
                           panel, rebalance_dates, cost_model)
        s = summary(res)
        profits.append(s["cagr"])
        dds.append(s["max_dd"])
    profit_pctile = float(np.mean([cand["cagr"] > p for p in profits]))
    dd_pctile = float(np.mean([cand["max_dd"] >= d for d in dds]))   # higher = shallower
    return {"profit_pctile": profit_pctile, "dd_pctile": dd_pctile,
            "beats_90": profit_pctile >= 0.9 and dd_pctile >= 0.5}
