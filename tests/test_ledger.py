import statistics

import pytest

from number7.research.ledger import Ledger, param_hash
from number7.research.registry import PreRegistration


def _prereg(**over):
    base = dict(
        family="momentum_v1", origin="human",
        mechanism="Cross-sectional momentum persists because institutional flows adjust slowly.",
        citations=["KB-02 Clenow"], expected_effect="top-decile spread > 0 net",
        falsification="WFE < 0.5 or DSR below hurdle",
        param_space={"lookback": [60, 90, 120], "top_n": [20, 25]},
    )
    base.update(over)
    return PreRegistration(**base)


def test_search_space_size():
    assert _prereg().search_space_size == 6


def test_register_and_trials_accounting(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    reg = led.register(_prereg())
    # (100, 22) is deliberately OUTSIDE the declared grid below, so it does not collide
    # with any of the 6 grid points logged next - family_trials counts DISTINCT param
    # combinations, so a colliding probe would silently undercount the "7" below.
    led.log_run(reg, code_sha="abc", snapshot_id="2026-07-02",
                params={"lookback": 100, "top_n": 22},
                metrics={"sharpe": 0.8, "n_obs": 500})
    assert led.family_trials("momentum_v1") == 6          # declared space dominates 1 run
    for lb in (60, 90, 120):
        for n in (20, 25):
            led.log_run(reg, code_sha="abc", snapshot_id="2026-07-02",
                        params={"lookback": lb, "top_n": n},
                        metrics={"sharpe": 0.1 * n / 20, "n_obs": 500})
    assert led.family_trials("momentum_v1") == 7          # 7 distinct param combos > declared 6
    assert led.var_of_trial_sharpes("momentum_v1") > 0


def test_family_trials_does_not_inflate_on_a_bugfix_rerun(tmp_path):
    """A legitimate bugfix re-run (same reg_id, same params, DIFFERENT code_sha - the
    code changed, the hypothesis did not) is the same trial executed again, not a new
    one. Seven re-runs of a single param combination must not push family_trials past
    the declared 6-point space: if raw row count were used instead, 15 such re-runs
    would drop the DSR hurdle from 0.98 to 0.95 for a hypothesis that was never actually
    widened (spec §11.4)."""
    led = Ledger(tmp_path / "ledger.duckdb")
    reg = led.register(_prereg())
    for i in range(7):
        led.log_run(reg, code_sha=f"sha{i}", snapshot_id="2026-07-02",
                    params={"lookback": 90, "top_n": 25},
                    metrics={"sharpe": 0.8, "n_obs": 500})
    assert led.family_trials("momentum_v1") == 6          # declared space, NOT 7 raw rows


def test_family_trials_increments_on_a_genuinely_different_param_combo(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    reg = led.register(_prereg())
    for lb, n in [(60, 20), (60, 25), (90, 20), (90, 25), (120, 20), (120, 25)]:
        led.log_run(reg, code_sha="abc", snapshot_id="2026-07-02",
                    params={"lookback": lb, "top_n": n},
                    metrics={"sharpe": 0.1, "n_obs": 500})
    assert led.family_trials("momentum_v1") == 6           # exactly the declared grid
    led.log_run(reg, code_sha="abc", snapshot_id="2026-07-02",
                params={"lookback": 200, "top_n": 15},      # a genuinely new combo,
                metrics={"sharpe": 0.1, "n_obs": 500})       # outside the declared space
    assert led.family_trials("momentum_v1") == 7            # now counted separately


def test_var_of_trial_sharpes_does_not_inflate_on_a_bugfix_rerun(tmp_path):
    """`var_of_trial_sharpes` feeds expected_max_sr(n_trials, var_trials) - the same
    statistic family_trials guards against gaming. A legitimate bugfix re-run (same
    params, DIFFERENT code_sha) is the same trial executed again, so it must contribute
    ONE sharpe observation (the mean of its re-run sharpes) to the variance, not one
    observation per row: if raw rows were used, a bugfix re-run could shrink the variance
    estimate and quietly ease the DSR hurdle. Runs with a genuinely different param combo
    must still contribute their own distinct observation."""
    led = Ledger(tmp_path / "ledger.duckdb")
    reg = led.register(_prereg())
    combo_a = [0.80, 0.81, 0.79, 0.80, 0.82]
    for i, sharpe in enumerate(combo_a):
        led.log_run(reg, code_sha=f"sha{i}", snapshot_id="2026-07-02",
                    params={"lookback": 90, "top_n": 25},
                    metrics={"sharpe": sharpe, "n_obs": 500})
    combo_b = [0.30, 0.29, 0.31]
    for i, sharpe in enumerate(combo_b):
        led.log_run(reg, code_sha=f"shb{i}", snapshot_id="2026-07-02",
                    params={"lookback": 60, "top_n": 20},
                    metrics={"sharpe": sharpe, "n_obs": 500})
    expected = statistics.pvariance(
        [statistics.mean(combo_a), statistics.mean(combo_b)])
    assert led.var_of_trial_sharpes("momentum_v1") == pytest.approx(expected)
    # sanity: raw-row variance (the buggy behavior) differs from the deduped one
    raw = statistics.pvariance(combo_a + combo_b)
    assert raw != pytest.approx(expected)


def test_scrapped_params_cannot_reenter(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    reg = led.register(_prereg())
    led.scrap(reg)
    with pytest.raises(ValueError, match="scrapped"):
        led.register(_prereg())


def test_param_hash_is_order_insensitive():
    assert param_hash({"a": 1, "b": 2}) == param_hash({"b": 2, "a": 1})


def test_reordered_param_space_cannot_bypass_scrap_guard(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    led.scrap(led.register(_prereg()))
    reordered = _prereg(param_space={"lookback": [120, 60, 90], "top_n": [25, 20]})
    with pytest.raises(ValueError, match="scrapped"):
        led.register(reordered)


def test_register_once_is_idempotent(tmp_path):
    """A re-run of the SAME pre-registration is the same hypothesis, not a new trial -
    repeated calls must not inflate the declared trial count (spec §11.4)."""
    led = Ledger(tmp_path / "ledger.duckdb")
    reg1 = led.register_once(_prereg())
    reg2 = led.register_once(_prereg())
    assert reg1 == reg2
    assert led.family_trials("momentum_v1") == 6          # declared space, not doubled


def test_register_once_still_registers_a_changed_param_space(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    reg1 = led.register_once(_prereg())
    changed = _prereg(param_space={"lookback": [60, 90, 120], "top_n": [20, 25, 30]})
    reg2 = led.register_once(changed)
    assert reg1 != reg2
    assert led.family_trials("momentum_v1") == 6 + 9      # both spaces now declared


def test_register_once_still_blocks_a_scrapped_space(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    led.scrap(led.register(_prereg()))
    with pytest.raises(ValueError, match="scrapped"):
        led.register_once(_prereg())
