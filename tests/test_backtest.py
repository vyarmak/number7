import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, StrategyManifest


class AllInA:
    manifest = StrategyManifest(name="all_in_a", family="test", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.close.columns)
        w["A"] = 1.0
        return w


def _panel(n=15):
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    a = 100 * np.cumprod(np.full(n, 1.01))
    b = np.full(n, 50.0)
    close = pd.DataFrame({"A": a, "B": b}, index=dates)
    ones = pd.DataFrame(True, index=dates, columns=["A", "B"])
    return PanelView(close=close, volume=close * 0 + 1e9,
                     unadjusted_close=close, in_index=ones)


def test_engine_timing_and_compounding():
    panel = _panel()
    rb = pd.DatetimeIndex([panel.close.index[2], panel.close.index[7]])
    res = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    assert res.equity.loc[rb[0]] == pytest.approx(1.0)
    expected = 1.01 ** (len(panel.close.loc[rb[0]:]) - 1)
    assert res.equity.iloc[-1] == pytest.approx(expected, rel=1e-9)
    assert res.turnover.loc[rb[0]] == pytest.approx(1.0)
    assert res.turnover.loc[rb[1]] == pytest.approx(0.0, abs=1e-12)


def test_costs_reduce_equity():
    panel = _panel()
    rb = pd.DatetimeIndex([panel.close.index[2]])
    free = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    paid = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=10.0))
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]
    assert paid.costs.loc[rb[0]] == pytest.approx(10.0 / 1e4, rel=1e-6)


def test_summary_keys():
    panel = _panel()
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([panel.close.index[2]]),
                       CostModel())
    s = summary(res)
    assert set(s) == {"cagr", "sharpe", "sortino", "max_dd", "profit_factor",
                      "hit_rate", "n_rebalances", "avg_turnover"}
