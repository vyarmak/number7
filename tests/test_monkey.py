import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import RandomTopN, StrategyManifest, full_slate
from number7.strategies.clenow import ClenowMomentum, ClenowParams
from number7.strategies.sizing import SizingConfig
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


def _clenow_panel(make_panel, n=600):
    """20 constituents with a clean momentum ordering, plus a rising SPY."""
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    data = {f"S{i:02d}": 100 * np.exp(0.0002 * i * np.arange(n)) for i in range(20)}
    data["SPY"] = 300 * np.exp(0.0004 * np.arange(n))
    close = pd.DataFrame(data, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False
    return make_panel(close, in_index=flags, high=close * 1.01, low=close * 0.99,
                      open_=close)


def test_monkeys_match_the_candidates_exposure_profile(make_panel):
    panel = _clenow_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[40:]
    cfg = SizingConfig(sleeve_equity=50_000.0)
    cm = CostModel(min_half_spread_bps=0.0)
    cand = run_backtest(ClenowMomentum(ClenowParams()), panel, rb, cm,
                        sizing=cfg, initial=50_000.0)
    v = monkey_test(cand, panel, rb, cm,
                    null_factory=lambda s: ClenowMomentum(ClenowParams(), shuffle_seed=s),
                    sizing=cfg, initial=50_000.0, n_monkeys=25, seed=1)
    assert v["avg_gross_monkeys"] == pytest.approx(v["avg_gross_candidate"], abs=0.15)
    assert 0.0 <= v["profit_pctile"] <= 1.0
