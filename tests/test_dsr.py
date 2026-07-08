import pytest

from number7.validation.dsr import dsr, dsr_hurdle, expected_max_sr, psr


def test_expected_max_sr_kb_textbook_value():
    # KB-07 §4a: 1,000 zero-edge trials at V=1 -> expected max Sharpe ≈ 3.26
    assert expected_max_sr(1000, 1.0) == pytest.approx(3.26, abs=0.02)


def test_psr_hand_value():
    # SR=0.1/period, 252 obs, gaussian -> z = 0.1*sqrt(251)/sqrt(1.005) ≈ 1.5805
    assert psr(0.1, 252, skew=0.0, kurt=3.0) == pytest.approx(0.943, abs=0.002)


def test_psr_fat_tails_reduce_confidence():
    assert psr(0.1, 252, skew=-1.0, kurt=8.0) < psr(0.1, 252, skew=0.0, kurt=3.0)


def test_dsr_penalizes_trials():
    base = dsr(0.15, 504, 0.0, 3.0, n_trials=1, var_trials=0.05)
    mined = dsr(0.15, 504, 0.0, 3.0, n_trials=200, var_trials=0.05)
    assert mined < base


def test_hurdle_tiers():
    assert dsr_hurdle(10, "human") == 0.98
    assert dsr_hurdle(30, "human") == 0.95
    assert dsr_hurdle(30, "llm") == 0.98
