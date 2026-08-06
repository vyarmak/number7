from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from number7.engine.costs import CostModel
from number7.strategies.clenow import (ANN_FACTOR, ATR_BURN_IN_MULT, ClenowMomentum,
                                       ClenowParams, slope_r2, wilder_atr)
from number7.strategies.sizing import SizingConfig
from number7.validation.causality import causality_violations, closed_loop_violations

P = ClenowParams()
NEED = max(P.lookback, P.ma_filter, P.atr_window * ATR_BURN_IN_MULT + 1)   # 101


def _series(n: int, daily: float, start: float = 100.0) -> np.ndarray:
    return start * np.exp(daily * np.arange(n))


def _panel(make_panel, *, movers: dict[str, float], n: int = 400,
           regime_daily: float = 0.0005, regime_start: float = 300.0):
    """Log-linear universe plus SPY. `movers` maps symbol -> daily log drift."""
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    data = {s: _series(n, d) for s, d in movers.items()}
    data["SPY"] = _series(n, regime_daily, regime_start)
    close = pd.DataFrame(data, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False                      # regime instrument is no constituent
    return make_panel(close, in_index=flags, high=close * 1.01, low=close * 0.99,
                      open_=close)


def test_planted_log_linear_trend_is_recovered_analytically():
    b = 0.0007
    slope, r2 = slope_r2(np.log(_series(90, b))[:, None])
    assert slope[0] == pytest.approx(b, rel=1e-12)
    assert r2[0] == pytest.approx(1.0, abs=1e-12)
    assert float(np.expm1(slope[0] * ANN_FACTOR)) == pytest.approx(np.expm1(b * 250))


def test_constant_log_price_has_undefined_r2():
    slope, r2 = slope_r2(np.log(np.full((90, 1), 50.0)))
    assert np.isnan(r2[0])


def test_wilder_atr_matches_the_pinned_recursion():
    n = 60
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    high = pd.DataFrame({"A": np.full(n, 102.0)}, index=idx)
    low = pd.DataFrame({"A": np.full(n, 100.0)}, index=idx)
    close = pd.DataFrame({"A": np.full(n, 101.0)}, index=idx)
    # constant bars: TR = 2.0 every day after the first, so seed = 2.0 and the
    # recursion (19 * 2 + 2) / 20 = 2.0 is a fixed point
    assert float(wilder_atr(high, low, close, 20)["A"]) == pytest.approx(2.0)

    # Perturb the last bar's RANGE, not its close. `close` is consumed only via shift(1),
    # so the final row's close is never any row's `prev` and mutating it cannot move the
    # ATR — an earlier version of this test did exactly that and asserted 2.0 == 2.0.
    high2, low2 = high.copy(), low.copy()
    high2.iloc[-1] = 110.0                      # widened bar: TR = max(10, |110-101|, |100-101|)
    got = float(wilder_atr(high2, low2, close, 20)["A"])
    assert got == pytest.approx((19 * 2.0 + 10.0) / 20)     # = 2.4, not the 2.0 fixed point
    assert got != pytest.approx(2.0)                        # the perturbation must register


def test_wilder_atr_uses_the_mean_seed_not_the_first_true_range():
    n = 40
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(0)
    close = pd.DataFrame({"A": 100 + np.cumsum(rng.normal(0, 1, n))}, index=idx)
    high, low = close + 1.0, close - 1.0
    prev = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev).abs(), (low - prev).abs())).iloc[1:]
    tail = tr.tail(P.atr_window * ATR_BURN_IN_MULT)
    manual = float(tail.iloc[:P.atr_window].mean().iloc[0])
    for v in tail["A"].to_numpy()[P.atr_window:]:
        manual = (19 * manual + float(v)) / 20
    assert float(wilder_atr(high, low, close, 20)["A"]) == pytest.approx(manual, rel=1e-12)


def test_gap_filter_fires_at_151bp_not_149(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001})
    o = panel.px_open.copy()
    prev = panel.px_close.shift(1)
    idx = o.index[-30]                               # inside the 90-session window
    # Set the perturbed open directly off the prior close so the gap ratio is exactly
    # 15.1%/14.9%; multiplying the (already open==close, drifting) existing open value
    # bakes in the day's own ~10bp drift and pushes 149bp over the 15% threshold too.
    o.loc[idx, "A"] = prev.loc[idx, "A"] * 1.151
    o.loc[idx, "B"] = prev.loc[idx, "B"] * 1.149
    strat = ClenowMomentum(ClenowParams(hold_top_pct=1.0))
    slate = strat.target_weights(make_panel(panel.px_close, in_index=panel.in_index,
                                            high=panel.px_high, low=panel.px_low, open_=o))
    assert slate.weights["A"] == 0.0
    assert slate.weights["B"] > 0.0


def test_ties_break_on_assetid_not_ticker_order(make_panel):
    panel = _panel(make_panel, movers={"ZZZ": 0.001, "AAA": 0.001})
    aid = pd.Series({"ZZZ": 10.0, "AAA": 99.0, "SPY": 3.0})
    v = make_panel(panel.px_close, in_index=panel.in_index, high=panel.px_high,
                   low=panel.px_low, open_=panel.px_open, assetid=aid)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)
    assert slate.rank["ZZZ"] < slate.rank["AAA"]     # identical scores, lower assetid wins


def test_short_history_embedded_nan_and_nonpositive_close_are_ineligible(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001},
                   n=NEED + 5)
    close = panel.px_close.copy()
    close.iloc[:-40, close.columns.get_loc("B")] = np.nan       # < NEED valid bars
    close.iloc[-50, close.columns.get_loc("C")] = np.nan        # embedded NaN
    close.iloc[-60, close.columns.get_loc("D")] = -1.0          # non-positive
    v = make_panel(close, in_index=panel.in_index, high=close * 1.01, low=close * 0.99,
                   open_=close)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)
    assert slate.weights[["B", "C", "D"]].eq(0.0).all()
    assert slate.weights["A"] > 0.0
    assert np.isfinite(slate.weights.to_numpy()).all()


def test_embedded_nan_in_high_within_the_atr_window_is_ineligible(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001})
    high = panel.px_high.copy()
    high.iloc[-50, high.columns.get_loc("A")] = np.nan     # inside the ATR burn-in window
    v = make_panel(panel.px_close, in_index=panel.in_index, high=high, low=panel.px_low,
                   open_=panel.px_open)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)
    assert slate.weights["A"] == 0.0
    assert slate.weights["B"] > 0.0


def test_embedded_nan_in_low_within_the_atr_window_is_ineligible(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001})
    low = panel.px_low.copy()
    low.iloc[-50, low.columns.get_loc("A")] = np.nan        # inside the ATR burn-in window
    v = make_panel(panel.px_close, in_index=panel.in_index, high=panel.px_high, low=low,
                   open_=panel.px_open)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)
    assert slate.weights["A"] == 0.0
    assert slate.weights["B"] > 0.0


def test_embedded_nan_in_open_within_the_gap_lookback_is_ineligible(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001})
    o = panel.px_open.copy()
    o.iloc[-30, o.columns.get_loc("A")] = np.nan             # inside the 90-session lookback
    v = make_panel(panel.px_close, in_index=panel.in_index, high=panel.px_high,
                   low=panel.px_low, open_=o)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)   # gap filter on
    assert slate.weights["A"] == 0.0
    assert slate.weights["B"] > 0.0


def test_zero_atr_never_produces_an_infinite_weight(make_panel):
    """Isolates the atr.gt(0.0) guard (clenow.py) from every other qualifier: FLAT rises
    smoothly for most of its history (so it clears the SMA100 filter and the R^2/slope
    preconditions with `use_r2=False`) and then goes perfectly flat for exactly the ATR
    burn-in window, so its ATR alone is zero while its rank and every other qualifier are
    unaffected. A literally-constant-forever FLAT would ALSO fail the SMA filter itself
    (close == its own mean, never strictly greater), which would make this test pass for
    the wrong reason regardless of the ATR guard - see the report's mutation evidence."""
    n = 400
    atr_window = 5
    plateau = atr_window * ATR_BURN_IN_MULT + 1              # exactly the ATR burn-in window
    rising = _series(n - plateau, 0.001)
    flat_close = np.concatenate([rising, np.full(plateau, rising[-1])])
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    close = pd.DataFrame({"FLAT": flat_close, "A": _series(n, 0.001),
                          "SPY": _series(n, 0.0005, 300.0)}, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False
    v = make_panel(close, in_index=flags, high=close, low=close, open_=close)   # ATR == 0
    p = ClenowParams(hold_top_pct=1.0, use_r2=False, atr_window=atr_window)
    slate = ClenowMomentum(p).target_weights(v)
    assert slate.rank["FLAT"] == 2.0            # ranked (not excluded upstream by R^2/slope)
    assert close["FLAT"].iloc[-1] > close["FLAT"].tail(100).mean()   # clears the SMA filter
    assert slate.weights["FLAT"] == 0.0
    assert np.isfinite(slate.weights.to_numpy()).all()


def test_regime_warmup_is_an_explicit_off_branch(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001}, n=NEED + 10)
    # NEED + 10 < regime_ma = 200, so SMA200 is undefined
    slate = ClenowMomentum(ClenowParams()).target_weights(panel)
    assert slate.admit_new is False


def test_regime_gate_flips_on_the_sma200_crossing(make_panel):
    up = _panel(make_panel, movers={"A": 0.001, "B": 0.001}, regime_daily=0.0008)
    down = _panel(make_panel, movers={"A": 0.001, "B": 0.001}, regime_daily=-0.0008)
    assert ClenowMomentum(ClenowParams()).target_weights(up).admit_new is True
    assert ClenowMomentum(ClenowParams()).target_weights(down).admit_new is False


def test_missing_regime_instrument_fails_safe(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001})
    v = make_panel(panel.px_close.drop(columns=["SPY"]),
                   in_index=panel.in_index.drop(columns=["SPY"]))
    assert ClenowMomentum(ClenowParams()).target_weights(v).admit_new is False


def test_regime_instrument_and_non_constituents_are_never_candidates(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.001 + i * 1e-5 for i in range(10)})
    slate = ClenowMomentum(ClenowParams(hold_top_pct=0.20)).target_weights(panel)
    assert slate.weights["SPY"] == 0.0 and pd.isna(slate.rank["SPY"])
    # denominator is the 10 constituents, not 11: floor(0.20 * 10) = 2 funded names
    assert int((slate.weights > 0).sum()) == 2


def test_ma_filter_excludes_a_name_below_its_sma100(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001})
    close = panel.px_close.copy()
    close.iloc[-1, close.columns.get_loc("A")] *= 0.5     # last close under SMA100
    v = make_panel(close, in_index=panel.in_index, high=close * 1.01, low=close * 0.99,
                   open_=close)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0, use_gap_filter=False)) \
        .target_weights(v)
    assert slate.weights["A"] == 0.0


def test_weights_are_absolute_atr_parity_not_normalized(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001})
    p = ClenowParams(hold_top_pct=1.0, use_gap_filter=False)
    slate = ClenowMomentum(p).target_weights(panel)
    funded = slate.weights[slate.weights > 0]
    assert len(funded) == 4
    assert funded.sum() != pytest.approx(1.0)        # never normalized (spec §6.5)
    atr = wilder_atr(panel.px_high, panel.px_low, panel.px_close, p.atr_window)
    expected = p.risk_factor * panel.px_close.iloc[-1]["A"] / atr["A"]
    assert funded["A"] == pytest.approx(expected, rel=1e-12)


def test_use_r2_false_ranks_on_bare_slope_and_can_flip_the_order(make_panel):
    n = 400
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    t = np.arange(n, dtype=float)
    rng = np.random.default_rng(3)
    smooth = 100.0 * np.exp(0.0006 * t)                        # lower slope, R^2 ~= 1.0
    noisy = 100.0 * np.exp(0.0011 * t + rng.normal(0, 0.05, n))  # higher slope, low R^2
    spy = 300.0 * np.exp(0.0005 * t)
    close = pd.DataFrame({"SMOOTH": smooth, "NOISY": noisy, "SPY": spy}, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False
    panel = make_panel(close, in_index=flags, high=close * 1.01, low=close * 0.99,
                       open_=close)
    p = ClenowParams(hold_top_pct=1.0, use_gap_filter=False)
    with_r2 = ClenowMomentum(p).target_weights(panel)
    without_r2 = ClenowMomentum(replace(p, use_r2=False)).target_weights(panel)
    assert with_r2.rank["SMOOTH"] < with_r2.rank["NOISY"]        # smooth's R^2 wins by default
    assert without_r2.rank["NOISY"] < without_r2.rank["SMOOTH"]  # bare slope favors the climb


def test_use_regime_false_disables_the_gate_entirely(make_panel):
    down = _panel(make_panel, movers={"A": 0.001, "B": 0.001}, regime_daily=-0.0008)
    assert ClenowMomentum(ClenowParams()).target_weights(down).admit_new is False
    assert ClenowMomentum(ClenowParams(use_regime=False)) \
        .target_weights(down).admit_new is True


def test_equal_weight_ablation_ignores_atr_parity(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.002, "C": 0.003, "D": 0.004})
    p = ClenowParams(hold_top_pct=1.0, use_gap_filter=False,
                     equal_weight=True, equal_weight_size=0.04)
    slate = ClenowMomentum(p).target_weights(panel)
    funded = slate.weights[slate.weights > 0]
    assert len(funded) == 4
    assert (funded == 0.04).all()          # NOT close/ATR parity -- that's the whole point


def test_shuffle_seed_is_a_function_of_the_date_not_the_call_count(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.001 + i * 1e-5 for i in range(20)})
    a, b = ClenowMomentum(ClenowParams(), shuffle_seed=7), ClenowMomentum(ClenowParams(),
                                                                          shuffle_seed=7)
    _ = a.target_weights(panel.masked_to(panel.sessions[-5]))   # burn a call on `a` only
    pd.testing.assert_series_equal(a.target_weights(panel).rank,
                                   b.target_weights(panel).rank)


class LeakyClenow(ClenowMomentum):
    """DELIBERATELY CHEATS: scores on the last bar of the stored panel instead of the
    view's last bar. Must be caught by both causality harnesses."""

    def __init__(self, params, full_px):
        super().__init__(params)
        self._full = full_px

    def target_weights(self, view):
        patched = type(view)(**{**view.__dict__, "px_close": self._full})
        return super().target_weights(patched)


def test_leaky_clenow_variant_is_caught(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.0005 * (i + 1) for i in range(6)})
    rb = pd.DatetimeIndex(panel.sessions[-40::10])
    # `p`, not the outer `panel`: causality_violations calls strategy_from_panel once with
    # the full panel and once with the truncated one, so a fixture that closes over the
    # outer panel leaks the SAME future tail on both legs and no difference is observable
    # (see LookaheadTrap's use of `p.px_close` in test_causality.py for the same pattern).
    assert causality_violations(lambda p: LeakyClenow(ClenowParams(), p.px_close),
                                panel, rb, truncate_last_n=15)


def test_clenow_is_causal_pointwise_and_closed_loop(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.0005 * (i + 1) for i in range(6)})
    rb = pd.DatetimeIndex(panel.sessions[-40::10])
    cfg = SizingConfig(sleeve_equity=50_000.0)
    assert causality_violations(lambda p: ClenowMomentum(ClenowParams()), panel, rb,
                                truncate_last_n=15) == []
    assert closed_loop_violations(lambda p: ClenowMomentum(ClenowParams()), panel, rb,
                                  CostModel(), sizing=cfg, truncate_last_n=15) == []


def test_cross_snapshot_stability_of_the_decision(make_panel):
    """A future dividend rescales pre-event adjusted levels; slope, R^2, MA relations, gap
    ratios and close/ATR are all invariant to a multiplicative factor, so the decision for
    a fixed historical signal date must not move (spec §12)."""
    panel = _panel(make_panel, movers={f"S{i}": 0.0005 * (i + 1) for i in range(6)})
    later = make_panel(panel.px_close * 1.037, in_index=panel.in_index,
                       high=panel.px_high * 1.037, low=panel.px_low * 1.037,
                       open_=panel.px_open * 1.037)
    a = ClenowMomentum(ClenowParams()).target_weights(panel)
    b = ClenowMomentum(ClenowParams()).target_weights(later)
    pd.testing.assert_series_equal(a.rank, b.rank)
    pd.testing.assert_series_equal(a.weights, b.weights)
    assert a.admit_new == b.admit_new
