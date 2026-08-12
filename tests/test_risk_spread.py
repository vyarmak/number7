import numpy as np
import pandas as pd
import pytest

from number7.risk.spread import corwin_schultz, spread_gate, spread_gate_frame

K = 3.0 - 2.0 * np.sqrt(2.0)


def _panel(h, low):
    idx = pd.date_range("2025-01-01", periods=len(h), freq="B")
    return (pd.DataFrame({"X": h}, index=idx, dtype=float),
            pd.DataFrame({"X": low}, index=idx, dtype=float))


def test_reproduces_closed_form_on_two_day_fixture():
    high, low = _panel([102.0, 103.0], [98.0, 99.0])
    beta = np.log(102.0 / 98.0) ** 2 + np.log(103.0 / 99.0) ** 2
    gamma = np.log(103.0 / 98.0) ** 2          # two-day high over two-day low
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / K - np.sqrt(gamma / K)
    expected = max(2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha)), 0.0)
    out = corwin_schultz(high, low)
    assert np.isnan(out.iloc[0, 0])            # first row has no prior day
    assert out.iloc[1, 0] == pytest.approx(expected, rel=1e-12)


def test_negative_estimates_floor_at_zero():
    # two tight days separated by a large overnight gap: beta tiny, gamma huge,
    # alpha strongly negative -> raw estimate negative -> floored at 0
    high, low = _panel([101.0, 121.0], [99.0, 119.0])
    beta = np.log(101.0 / 99.0) ** 2 + np.log(121.0 / 119.0) ** 2
    gamma = np.log(121.0 / 99.0) ** 2
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / K - np.sqrt(gamma / K)
    assert alpha < 0                            # fixture sanity: raw estimate IS negative
    out = corwin_schultz(high, low)
    assert out.iloc[1, 0] == 0.0


def test_zero_median_liquid_name_is_not_blocked_by_noise():
    n = 400
    high = [100.0001] * n                       # ~zero CS estimate every day
    low = [100.0] * n
    h, low_df = _panel(high, low)
    blocked = spread_gate(h, low_df, spread_floor=0.0010)
    assert not blocked["X"]                     # floor governs, 2 x 0 does not block


def test_blowout_triggers_against_lagged_baseline():
    n = 400
    high = [100.5] * n
    low = [100.0] * n
    for i in range(n - 30, n):                 # last 30 sessions: spread explodes
        high[i], low[i] = 103.0, 100.0
    h, low_df = _panel(high, low)
    assert spread_gate(h, low_df)["X"]


def test_insufficient_history_is_not_blocked():
    high, low = _panel([101.0] * 40, [100.0] * 40)
    assert not spread_gate(high, low)["X"]      # baseline NaN -> gate does not fire


def test_frame_row_equals_gate_on_truncated_history():
    """spread_gate_frame.loc[d] must equal spread_gate on data truncated at d for
    EVERY d: the engine precomputes the frame once per run and slices per signal
    date, so any drift here is a causality or parity break, not a perf detail."""
    rng = np.random.default_rng(7)
    n, cols = 320, ["A", "B", "C"]
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    close = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, len(cols))), axis=0))
    spread = np.abs(rng.normal(0.002, 0.002, (n, len(cols))))
    high = pd.DataFrame(close * (1 + spread), index=idx, columns=cols)
    low = pd.DataFrame(close * (1 - spread), index=idx, columns=cols)
    high.iloc[290:, 0] = low.iloc[290:, 0] * 1.05      # A: recent blowout
    high.iloc[:100, 1] = np.nan                        # B: short history
    frame = spread_gate_frame(high, low)
    assert frame.index.equals(idx) and list(frame.columns) == cols
    for d in [idx[260], idx[280], idx[300], idx[-1]]:
        recomputed = spread_gate(high.loc[:d], low.loc[:d])
        pd.testing.assert_series_equal(frame.loc[d], recomputed, check_names=False)
    assert frame.loc[idx[-1], "A"]                     # the blowout actually fires
