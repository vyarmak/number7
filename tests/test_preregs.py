import pytest

from number7.research.ledger import Ledger
from number7.research.preregs import (CANDIDATE_FAMILY, CLENOW_DIAGNOSTIC,
                                      CLENOW_REFERENCE, CLENOW_SEARCHED,
                                      DIAGNOSTIC_FAMILY, RISK_OVERLAY_ABLATION)
from number7.validation.dsr import dsr_hurdle


def test_risk_overlay_ablation_is_diagnostic_and_two_cell():
    assert RISK_OVERLAY_ABLATION.family == DIAGNOSTIC_FAMILY
    assert RISK_OVERLAY_ABLATION.param_space == {"overlay": ["on", "off"]}
    assert RISK_OVERLAY_ABLATION.search_space_size == 2


def test_reference_is_a_single_point():
    assert CLENOW_REFERENCE.search_space_size == 1
    assert all(len(v) == 1 for v in CLENOW_REFERENCE.param_space.values())


def test_pinned_constants_are_not_in_any_searched_space():
    pinned = {"ann_factor", "atr_burn_in_mult", "smoothing", "drift_band_mode"}
    for prereg in (CLENOW_REFERENCE, CLENOW_SEARCHED):
        assert not pinned & set(prereg.param_space)


def test_searched_space_is_exactly_the_declared_parameters():
    assert set(CLENOW_SEARCHED.param_space) == {
        "lookback", "atr_window", "ma_filter", "regime_ma", "gap_threshold",
        "risk_factor", "hold_top_pct", "max_positions", "drift_band"}


def test_diagnostics_live_in_their_own_family():
    assert CLENOW_DIAGNOSTIC.family == DIAGNOSTIC_FAMILY != CANDIDATE_FAMILY


def test_diagnostic_runs_do_not_inflate_the_candidate_trial_count(tmp_path):
    led = Ledger(tmp_path / "trials.duckdb")
    ref = led.register(CLENOW_REFERENCE)
    diag = led.register(CLENOW_DIAGNOSTIC)
    for i in range(12):
        led.log_run(diag, "sha", "snap", {"ablation": f"a{i}"}, {"sharpe": 0.5, "n_obs": 100})
    led.log_run(ref, "sha", "snap", {"profile": "reference"}, {"sharpe": 0.8, "n_obs": 100})
    assert led.family_trials(CANDIDATE_FAMILY) == 1
    assert dsr_hurdle(led.family_trials(CANDIDATE_FAMILY), CLENOW_REFERENCE.origin) == 0.98


def test_registering_the_searched_space_twice_is_a_duplicate_not_a_bypass(tmp_path):
    led = Ledger(tmp_path / "trials.duckdb")
    reg = led.register(CLENOW_SEARCHED)
    led.scrap(reg)
    with pytest.raises(ValueError, match="scrapped"):
        led.register(CLENOW_SEARCHED)
