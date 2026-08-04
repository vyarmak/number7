import numpy as np
import pandas as pd

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import RandomTopN, StrategyManifest, full_slate
from number7.validation.monkey import monkey_test


class BestDrift:
    """Cheats mildly on synthetic data: always holds the known drifting winner."""

    manifest = StrategyManifest(name="best", family="t", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.px_close.columns)
        w["W"] = 1.0
        return full_slate(w)


def _panel_with_winner(make_panel, n=504, seed=4):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    cols = {f"S{i}": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))) for i in range(10)}
    cols["W"] = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n)))
    close = pd.DataFrame(cols, index=dates)
    return make_panel(close)


def test_winner_beats_monkeys_and_null_does_not(make_panel):
    panel = _panel_with_winner(make_panel)
    rb = weekly_rebalances(panel.sessions)
    cm = CostModel(min_half_spread_bps=0.0)
    winner = run_backtest(BestDrift(), panel, rb, cm)
    verdict = monkey_test(winner, panel, rb, cm, n_monkeys=200, seed=1)
    assert verdict["profit_pctile"] >= 0.9

    null = run_backtest(RandomTopN(n=1, seed=99), panel, rb, cm)
    null_verdict = monkey_test(null, panel, rb, cm, n_monkeys=200, seed=1)
    assert null_verdict["profit_pctile"] < 0.9
