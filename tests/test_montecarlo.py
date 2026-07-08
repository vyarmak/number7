import numpy as np

from number7.validation.montecarlo import block_bootstrap_dd


def test_bootstrap_bands_are_sane_and_deterministic():
    rng = np.random.default_rng(2)
    rets = rng.normal(0.0004, 0.01, 1000)
    a = block_bootstrap_dd(rets, block=10, n=500, seed=7)
    b = block_bootstrap_dd(rets, block=10, n=500, seed=7)
    assert a == b
    assert a["dd_p99"] <= a["dd_p95"] <= 0
    lo, hi = a["sharpe_ci90"]
    assert lo < hi


def test_invalid_params_rejected():
    import pytest
    rets = np.random.default_rng(1).normal(0, 0.01, 100)
    with pytest.raises(ValueError):
        block_bootstrap_dd(rets, block=0)
    with pytest.raises(ValueError):
        block_bootstrap_dd(rets, n=0)
    with pytest.raises(ValueError):
        block_bootstrap_dd([])
