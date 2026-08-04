import pandas as pd

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.live import build_panel, compute_live_targets
from number7.engine.strategy import RandomTopN


def test_golden_replay_engine_equals_live_path(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[3]])
    strat_engine, strat_live = RandomTopN(n=1, seed=3), RandomTopN(n=1, seed=3)
    res = run_backtest(strat_engine, panel, rb, CostModel())
    for t in rb:
        live = compute_live_targets(strat_live, panel, asof=t)
        pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)
