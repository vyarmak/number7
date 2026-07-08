import numpy as np
import pandas as pd

from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import PanelView, RandomTopN


def _synthetic_panel(n_days=756, n_sym=30, seed=11) -> PanelView:
    """Zero-drift GBM universe: no strategy should make money here pre-cost."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_days, freq="B")
    rets = rng.normal(0.0, 0.01, size=(n_days, n_sym))
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates,
                         columns=[f"S{i:02d}" for i in range(n_sym)])
    ones = pd.DataFrame(True, index=dates, columns=close.columns)
    return PanelView(close=close, volume=close * 0 + 1e9, unadjusted_close=close,
                     in_index=ones)


def test_null_strategy_earns_nothing_pre_cost():
    panel = _synthetic_panel()
    rb = weekly_rebalances(panel.close.index)
    cm = CostModel(commission_bps=0.0, min_half_spread_bps=0.0)
    cagrs, hits = [], []
    for seed in range(8):
        s = summary(run_backtest(RandomTopN(n=5, seed=seed), panel, rb, cm))
        cagrs.append(s["cagr"])
        hits.append(s["hit_rate"])
    assert abs(float(np.mean(cagrs))) < 0.05          # ~zero edge on zero-drift data
    assert 0.35 < float(np.mean(hits)) < 0.65
