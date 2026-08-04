import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.strategy import StrategyManifest


class AllInA:
    manifest = StrategyManifest(name="all_in_a", family="test", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.px_close.columns)
        w["A"] = 1.0
        return w


def _panel(make_panel, n=15):
    dates = pd.date_range("2026-01-05", periods=n, freq="B")
    a = 100 * np.cumprod(np.full(n, 1.01))
    b = np.full(n, 50.0)
    close = pd.DataFrame({"A": a, "B": b}, index=dates)
    return make_panel(close)


def test_engine_timing_and_compounding(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[7]])
    res = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    assert res.equity.loc[rb[0]] == pytest.approx(1.0)
    expected = 1.01 ** (len(panel.tr_close.loc[rb[0]:]) - 1)
    assert res.equity.iloc[-1] == pytest.approx(expected, rel=1e-9)
    assert res.turnover.loc[rb[0]] == pytest.approx(1.0)
    assert res.turnover.loc[rb[1]] == pytest.approx(0.0, abs=1e-12)


def test_costs_reduce_equity(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2]])
    free = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    paid = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=10.0))
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]
    assert paid.costs.loc[rb[0]] == pytest.approx(10.0 / 1e4, rel=1e-6)


def test_summary_keys(make_panel):
    panel = _panel(make_panel)
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([panel.sessions[2]]),
                       CostModel())
    s = summary(res)
    assert set(s) == {"cagr", "sharpe", "sortino", "max_dd", "profit_factor",
                      "hit_rate", "n_rebalances", "avg_turnover"}
