import pandas as pd

from number7.benchmarks.ew import EqualWeightIndex, gate6
from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.live import build_panel


def test_ew_benchmark_holds_members_only(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.sessions[2]])
    res = run_backtest(EqualWeightIndex(), panel, rb, CostModel())
    w = res.weights.loc[rb[0]]
    assert w["AAPL"] > 0 and w["SPY"] == 0.0
    assert abs(w.sum() - 1.0) < 1e-9
    assert not build_panel(fake_snapshot).in_index["SPY"].any()


def test_gate6_flags_too_good():
    cand = {"sharpe": 2.5, "cagr": 0.4}
    bench = {"sharpe": 1.0, "cagr": 0.1}
    g = gate6(cand, bench)
    assert g["suspicious"] and abs(g["excess_cagr"] - 0.3) < 1e-12
