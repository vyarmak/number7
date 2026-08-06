from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.live import build_panel, compute_live_targets
from number7.engine.strategy import RandomTopN, Slate, StrategyManifest
from number7.strategies.sizing import SizingConfig, holdings_from_shares


class TwoNames:
    manifest = StrategyManifest(name="two", family="test", origin="human", params={})

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w["AAPL"], w["ATVI"] = 0.6, 0.5
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank["AAPL"], rank["ATVI"] = 1.0, 2.0
        return Slate(weights=w, rank=rank, admit_new=True)


class OneName:
    """Always wants A, oblivious to whether A still has a quote."""

    manifest = StrategyManifest(name="one", family="test", origin="human", params={})

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w["A"] = 1.0
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank["A"] = 1.0
        return Slate(weights=w, rank=rank, admit_new=True)


def test_golden_replay_engine_equals_live_path(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[3]])
    res = run_backtest(RandomTopN(n=1, seed=3), panel, rb, CostModel())
    for t in rb:
        live = compute_live_targets(RandomTopN(n=1, seed=3), panel, asof=t)
        pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)


def test_golden_replay_through_resolution_and_band(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[3]])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, min_position_dollars=0.0,
                       drift_band=0.05)
    res = run_backtest(TwoNames(), panel, rb, CostModel(), sizing=cfg)
    for t in rb:
        live = compute_live_targets(
            TwoNames(), panel, asof=t,
            current=res.state_at_signal.loc[t],
            sizing=replace(cfg, sleeve_equity=float(res.equity_at_signal.loc[t])),
            # stale_periods is recorded POST-trade for each date, so the counter the
            # resolver consumed at t is the previous rebalance's row.
            stale_periods=res.stale_periods.shift(1).fillna(0).loc[t])
        pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)


def test_live_path_masks_unquoted_names_like_the_engine(make_panel):
    dates = pd.date_range("2026-01-05", periods=10, freq="B")
    close = pd.DataFrame({"A": 100.0, "B": 50.0}, index=dates)
    close.loc[dates[5]:, "A"] = np.nan                    # A stops trading
    panel = make_panel(close)
    rb = pd.DatetimeIndex([dates[2], dates[8]])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0)
    res = run_backtest(OneName(), panel, rb, CostModel(min_half_spread_bps=0.0), sizing=cfg)
    t = rb[1]
    live = compute_live_targets(
        OneName(), panel, asof=t,
        current=res.state_at_signal.loc[t],
        sizing=replace(cfg, sleeve_equity=float(res.equity_at_signal.loc[t])),
        stale_periods=res.stale_periods.shift(1).fillna(0).loc[t])
    pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)
    assert live["A"] == pytest.approx(0.0)   # A has no quote at the signal date - never held


def test_live_holdings_are_built_from_shares_not_market_value(fake_snapshot):
    panel = build_panel(fake_snapshot)
    sig = panel.sessions[2]
    cur = holdings_from_shares({"AAPL": 10}, panel.raw_close.loc[sig], sleeve_equity=10_000.0)
    assert cur["AAPL"] == pytest.approx(10 * float(panel.raw_close.loc[sig, "AAPL"]) / 10_000.0)


def test_live_targets_refuse_an_unknown_book_when_sizing_is_supplied(fake_snapshot):
    """spec §8.4: degraded broker truth degrades to hold-state, never to treating an
    unknown position as flat. Under regime-off, resolve_book restricts admission to
    names with current > 0, so defaulting `current` to zeros would liquidate the sleeve
    on a caller that simply forgot the argument."""
    panel = build_panel(fake_snapshot)
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, min_position_dollars=0.0)
    with pytest.raises(ValueError, match="unknown book must not be treated as flat"):
        compute_live_targets(TwoNames(), panel, asof=panel.sessions[3], sizing=cfg)


def test_live_targets_accept_an_explicitly_flat_book(fake_snapshot):
    """A caller that genuinely holds nothing says so explicitly, and still gets a book."""
    panel = build_panel(fake_snapshot)
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, min_position_dollars=0.0)
    flat = pd.Series(0.0, index=panel.px_close.columns)
    w = compute_live_targets(TwoNames(), panel, asof=panel.sessions[3],
                             current=flat, sizing=cfg)
    assert w.sum() > 0        # regime is on for TwoNames, so an explicit flat book fills
