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
    led.log_run(reg, code_sha="abc", snapshot_id="2026-07-02",
                params={"lookback": 90, "top_n": 25},
                metrics={"sharpe": 0.8, "n_obs": 500})
    assert led.family_trials("momentum_v1") == 6          # declared space dominates 1 run
    for lb in (60, 90, 120):
        for n in (20, 25):
            led.log_run(reg, code_sha="abc", snapshot_id="2026-07-02",
                        params={"lookback": lb, "top_n": n},
                        metrics={"sharpe": 0.1 * n / 20, "n_obs": 500})
    assert led.family_trials("momentum_v1") == 7          # 7 runs > declared 6
    assert led.var_of_trial_sharpes("momentum_v1") > 0


def test_scrapped_params_cannot_reenter(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    reg = led.register(_prereg())
    led.scrap(reg)
    with pytest.raises(ValueError, match="scrapped"):
        led.register(_prereg())


def test_param_hash_is_order_insensitive():
    assert param_hash({"a": 1, "b": 2}) == param_hash({"b": 2, "a": 1})
