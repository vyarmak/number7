import numpy as np
import pandas as pd
import pytest

from number7.engine.costs import CostModel, corwin_schultz, impact_cost


def test_corwin_schultz_hand_value():
    # H/L = e^0.02 every day and across the 2-day span -> S ≈ 0.02004 (hand-derived)
    n = 40
    close = pd.Series(100.0, index=pd.date_range("2026-01-01", periods=n, freq="B"))
    high, low = close * np.exp(0.02), close
    s = corwin_schultz(high, low, window=21)
    assert s.iloc[-1] == pytest.approx(0.02004, abs=1e-3)   # shifted: known-at-t alignment


def test_corwin_schultz_zero_range_is_zero():
    idx = pd.date_range("2026-01-01", periods=30, freq="B")
    s = corwin_schultz(pd.Series(100.0, index=idx), pd.Series(100.0, index=idx))
    assert s.iloc[-1] == pytest.approx(0.0, abs=1e-12)


def test_impact_hand_value():
    assert impact_cost(0.01, 0.02) == pytest.approx((2 / 3) * 0.02 * 0.1, rel=1e-9)


def test_one_way_cost_floors_spread():
    cm = CostModel(commission_bps=0.0, min_half_spread_bps=2.0)
    c = cm.one_way_cost(spread_est=0.0, q_over_adv=0.0, sigma=0.02)
    assert c == pytest.approx(0.0002, rel=1e-9)
