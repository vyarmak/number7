import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import Slate, StrategyManifest, full_slate
from number7.risk.overlay import RiskConfig
from number7.strategies.sizing import SizingConfig


class AllInA:
    manifest = StrategyManifest(name="all_in_a", family="test", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.px_close.columns)
        w["A"] = 1.0
        return full_slate(w)


class FixedSlate:
    """Emits a constant absolute weight for A and B, always admitting."""

    manifest = StrategyManifest(name="fixed", family="test", origin="human", params={})

    def __init__(self, weights: dict) -> None:
        self._w = weights

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w.update(pd.Series(self._w))
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank[list(self._w)] = np.arange(1.0, len(self._w) + 1.0)
        return Slate(weights=w, rank=rank, admit_new=True)


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


def test_cagr_is_zero_for_a_flat_book_regardless_of_initial_capital(make_panel):
    """Equity that never moves from `initial` must report cagr == 0.0. Exponentiating the
    raw equity LEVEL (a bug fixed in this commit) instead reports ~0.62 here because eq is
    a dollar level (50_000), not a growth multiple."""
    panel = _panel(make_panel)
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([]), CostModel(), initial=50_000.0)
    s = summary(res)
    assert s["cagr"] == pytest.approx(0.0, abs=1e-12)


def test_cagr_is_scale_invariant_in_initial_capital(make_panel):
    """CAGR measures growth, not level: the same strategy/path must report the same cagr
    whether the book starts at 1.0 or 50_000.0."""
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[7]])
    unit = summary(run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0),
                                initial=1.0))
    dollars = summary(run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0),
                                   initial=50_000.0))
    assert dollars["cagr"] == pytest.approx(unit["cagr"], rel=1e-9)


def test_state_at_signal_is_the_prior_close_book(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[7]])
    res = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    assert res.state_at_signal.loc[rb[0]].sum() == pytest.approx(0.0)   # still in cash
    assert res.state_at_signal.loc[rb[1]]["A"] == pytest.approx(1.0)
    # equity used for sizing is T-1's, never T's
    sig = panel.sessions[panel.sessions.get_loc(rb[1]) - 1]
    assert res.equity_at_signal.loc[rb[1]] == pytest.approx(res.equity.loc[sig])


def test_cash_earns_the_pinned_rate(make_panel):
    panel = _panel(make_panel)
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([]), CostModel(),
                       cash_annual_rate=0.04)
    n = len(panel.sessions)
    assert res.equity.iloc[-1] == pytest.approx((1.04 ** (1 / 252)) ** n, rel=1e-9)


def test_resolver_runs_when_sizing_is_supplied(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2]])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, min_position_dollars=0.0)
    res = run_backtest(FixedSlate({"A": 0.9}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg)
    assert res.weights.loc[rb[0], "A"] == pytest.approx(0.30)     # capped by the resolver


def test_drift_band_retention_produces_zero_turnover(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[3]])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0,
                       drift_band=0.50)
    res = run_backtest(FixedSlate({"A": 0.5}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg)
    assert res.turnover.loc[rb[1]] == pytest.approx(0.0, abs=1e-12)


def test_stale_counter_increments_on_hold_and_resets_on_trade(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex(panel.sessions[2:6])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0,
                       drift_band=0.50, forced_resize_periods=99)
    res = run_backtest(FixedSlate({"A": 0.5}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg)
    # stale_periods stores the POST-trade counter for date t (see docstring on
    # BacktestResult.stale_periods and run_backtest): rb[0] enters (resets to 0), rb[1]
    # holds (0 -> 1), rb[3] is the third consecutive hold since entry (0 -> 1 -> 2 -> 3).
    assert res.stale_periods.loc[rb[1], "A"] == 1     # first hold after the entry at rb[0]
    assert res.stale_periods.loc[rb[3], "A"] == 3     # held through rb[1], rb[2], and rb[3]


def test_start_limits_the_loop_and_initial_weights_seed_it(make_panel):
    panel = _panel(make_panel)
    seed = pd.Series(0.0, index=panel.px_close.columns)
    seed["A"] = 1.0
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([]), CostModel(),
                       start=panel.sessions[5], initial_weights=seed)
    assert res.equity.loc[:panel.sessions[4]].isna().all()
    assert res.equity.iloc[-1] == pytest.approx(1.01 ** (len(panel.sessions) - 5), rel=1e-9)
    assert res.final_weights["A"] == pytest.approx(1.0)


def test_final_stale_matches_the_last_rebalance_counter(make_panel):
    """final_stale has no other dedicated coverage — walk-forward's fold carry-over
    (Task 6) is its first real consumer, so this pins the field directly."""
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex(panel.sessions[2:6])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0,
                       drift_band=0.50, forced_resize_periods=99)
    res = run_backtest(FixedSlate({"A": 0.5}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg)
    assert res.final_stale["A"] == res.stale_periods.loc[rb[-1], "A"]
    assert res.final_stale["A"] == 3


def test_start_on_a_rebalance_date_that_is_the_first_loop_session(make_panel):
    """The walk-forward fold boundary: `start` lands exactly on a rebalance date that is
    also the first SIMULATED session (but not the panel's first session). The `t !=
    sessions[0]` skip in run_backtest refers to the panel's first session, not the loop's
    first session, so this rebalance must resolve using the seeded initial_weights /
    initial_stale rather than being silently skipped."""
    panel = _panel(make_panel)
    start = panel.sessions[5]
    rb = pd.DatetimeIndex([start])
    current = pd.Series({"A": 0.50})
    stale = pd.Series({"A": 10})
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0,
                       drift_band=0.50, forced_resize_periods=5)
    res = run_backtest(FixedSlate({"A": 0.55}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg, start=start, initial_weights=current, initial_stale=stale)
    # relative drift = |0.55-0.50|/0.55 ~= 0.09, within drift_band=0.50 - would retain at
    # zero turnover if the seeded stale counter (10) were ignored. forced_resize_periods=5
    # forces the resize instead, proving initial_stale reached the resolver on this very
    # first loop session.
    assert res.rebalance_dates[0] == start
    assert res.turnover.loc[start] == pytest.approx(0.05, abs=1e-9)
    assert res.weights.loc[start, "A"] == pytest.approx(0.55)
    assert res.final_stale["A"] == 0     # resets on trade


def test_delisted_holding_is_exited_at_the_next_rebalance_and_counted(make_panel):
    dates = pd.date_range("2026-01-05", periods=10, freq="B")
    close = pd.DataFrame({"A": 100.0, "B": 50.0}, index=dates)
    close.loc[dates[5]:, "A"] = np.nan                    # A stops trading
    panel = make_panel(close)
    rb = pd.DatetimeIndex([dates[2], dates[8]])
    res = run_backtest(FixedSlate({"A": 1.0}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=SizingConfig(sleeve_equity=1.0, position_cap=1.0,
                                           min_position_dollars=0.0))
    assert res.weights.loc[rb[1]].sum() == pytest.approx(0.0)   # A is unrankable -> exited
    assert int(res.delisting_exits.loc[rb[1]]) == 1
    assert np.isfinite(res.equity.iloc[-1])


# ---------------------------------------------------------------- risk overlay wiring

def _risk_panel(make_panel, n=300, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-05", periods=n, freq="B")
    cols = ["A", "B", "C", "D"]
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, (n, 4)), axis=0)),
        index=idx, columns=cols)
    return make_panel(close, gics_sector=pd.Series("TestSector", index=cols))


class FourEqual:
    manifest = StrategyManifest(name="four", family="test", origin="human", params={})

    def target_weights(self, view) -> Slate:
        cols = view.px_close.columns
        w = pd.Series(0.25, index=cols)
        rank = pd.Series(np.arange(1.0, len(cols) + 1.0), index=cols)
        return Slate(weights=w, rank=rank, admit_new=True)


def test_backtest_records_risk_k_and_final_k(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-8:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0, risk_cfg=RiskConfig())
    assert len(res.risk_k) == len(res.rebalance_dates)
    assert (res.risk_k > 0).all() and (res.risk_k <= 1.0).all()
    assert res.final_k == pytest.approx(float(res.risk_k.iloc[-1]))


def test_backtest_k_ratchets_up_slowly(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-8:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0, risk_cfg=RiskConfig(), initial_k=0.20)
    ks = res.risk_k.to_numpy()
    assert (np.diff(ks) <= 0.10 + 1e-9).all()       # up moves capped at up_step


def test_backtest_risk_requires_sizing(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-4:]
    with pytest.raises(ValueError, match="risk_cfg requires sizing"):
        run_backtest(FourEqual(), panel, rb, CostModel(), risk_cfg=RiskConfig())


def test_backtest_records_risk_diag(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-6:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0, risk_cfg=RiskConfig())
    assert set(res.risk_diag) == set(res.rebalance_dates)
    assert {"beta", "avg_corr", "applied_k"} <= set(next(iter(res.risk_diag.values())))


def test_backtest_without_risk_has_default_risk_fields(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-8:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg, initial=50_000.0)
    assert res.final_k == 1.0 and len(res.risk_k) == 0 and res.risk_diag is None
