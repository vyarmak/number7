from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from number7.engine.costs import CostModel
from number7.research.calibrate_clenow import (PROFILES, exposure_metrics,
                                               regime_episodes, run_profile,
                                               turnover_at_transitions)
from number7.strategies.clenow import ClenowParams


def _regime_panel(make_panel, n=700):
    """SPY rises, falls below its SMA200, then recovers — one regime-off episode."""
    dates = pd.date_range("2019-01-01", periods=n, freq="B")
    spy = np.concatenate([300 * np.exp(0.0008 * np.arange(300)),
                          300 * np.exp(0.0008 * 299) * np.exp(-0.0025 * np.arange(150)),
                          300 * np.exp(0.0008 * 299) * np.exp(-0.0025 * 149)
                          * np.exp(0.0012 * np.arange(n - 450))])
    data = {f"S{i:02d}": 100 * np.exp(0.0003 * (i + 1) * np.arange(n)) for i in range(12)}
    data["SPY"] = spy
    close = pd.DataFrame(data, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False
    return make_panel(close, in_index=flags, high=close * 1.01, low=close * 0.99,
                      open_=close)


def test_both_profiles_are_frozen_and_distinct():
    assert set(PROFILES) == {"reference", "deployable"}
    ref_p, ref_s = PROFILES["reference"]
    dep_p, dep_s = PROFILES["deployable"]
    assert (ref_p, ref_s) != (dep_p, dep_s)
    assert dep_s.position_cap == 0.10 and dep_s.min_position_dollars == 1000.0


def test_regime_episodes_are_scored_over_the_whole_history(make_panel):
    panel = _regime_panel(make_panel)
    eps = regime_episodes(panel, ClenowParams())
    assert len(eps) >= 1
    e = eps[0]
    assert set(e) == {"start", "end", "sessions", "index_return_through_episode",
                      "post_episode_return", "hit"}
    assert e["hit"] is (e["index_return_through_episode"] < 0)


def test_exposure_metrics_report_average_gross_as_first_class(make_panel):
    panel = _regime_panel(make_panel)
    params, sizing = PROFILES["deployable"]
    res = run_profile(panel, params, sizing, CostModel(min_half_spread_bps=0.0))
    m = exposure_metrics(res, panel)
    assert 0.0 < m["avg_gross"] <= 1.0
    assert set(m) >= {"avg_gross", "return_per_unit_exposure", "beta_vs_index", "sharpe"}


def test_turnover_at_transitions_is_reported_separately():
    """Synthetic turnover with sharp spikes ONLY at the two transition marks, 14 days
    apart from every other observation (well outside the +/-7d matching window) so
    neighbours cannot leak in. An implementation that ignored the matching entirely
    (e.g. returning the plain average for both fields) would fail every assertion here."""
    dates = pd.date_range("2020-01-07", periods=10, freq="14D")
    turnover = pd.Series(0.02, index=dates)
    turnover.loc[dates[3]] = 0.80
    turnover.loc[dates[7]] = 0.80
    episodes = [{"start": str(dates[3].date()), "end": str(dates[3].date())},
               {"start": str(dates[7].date()), "end": str(dates[7].date())}]
    result = SimpleNamespace(turnover=turnover)
    t = turnover_at_transitions(result, episodes)
    assert set(t) == {"avg_turnover", "avg_turnover_at_transitions", "n_transitions"}
    assert t["n_transitions"] == 2
    assert t["avg_turnover_at_transitions"] == pytest.approx(0.80)
    assert t["avg_turnover"] == pytest.approx(float(turnover.mean()))
    assert t["avg_turnover_at_transitions"] > t["avg_turnover"] * 4


def test_deployable_profile_never_breaches_its_own_limits(make_panel):
    """Contract-wide (spec §12): every resolved book on a real run passes validate_book."""
    from number7.strategies.sizing import validate_book
    panel = _regime_panel(make_panel)
    params, sizing = PROFILES["deployable"]
    res = run_profile(panel, params, sizing, CostModel(min_half_spread_bps=0.0))
    for t in res.rebalance_dates:
        validate_book(res.weights.loc[t], sizing)
