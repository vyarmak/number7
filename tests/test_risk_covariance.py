import numpy as np
import pandas as pd
import pytest

from number7.risk.covariance import ewma_covariance


def _rets(n=300, cols=("A", "B", "C"), seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(rng.normal(0, 0.01, (n, len(cols))), index=idx, columns=list(cols))


def test_matches_hand_computed_weighted_moments():
    r = _rets(n=50)
    out = ewma_covariance(r, halflife=10, min_obs=5, shrinkage=0.0)
    w = 0.5 ** (np.arange(49, -1, -1) / 10.0)
    w = w / w.sum()
    x = r.to_numpy()
    expected = (x * w[:, None]).T @ x * 252.0     # zero-mean EWMA, renormalized weights
    np.testing.assert_allclose(out.sigma.to_numpy(), expected, rtol=1e-10)


def test_recent_observations_dominate():
    r = _rets(n=200)
    r.iloc[-20:, 0] *= 5.0                        # recent vol spike in A only
    out = ewma_covariance(r, halflife=10, min_obs=5, shrinkage=0.0)
    flat = ewma_covariance(r, halflife=10_000, min_obs=5, shrinkage=0.0)
    assert out.sigma.loc["A", "A"] > 2.0 * flat.sigma.loc["A", "A"]


def test_shrinkage_pulls_offdiagonals_toward_constant_correlation():
    r = _rets()
    shrunk = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=1.0)
    corr = shrunk.sigma.to_numpy() / np.sqrt(
        np.outer(np.diag(shrunk.sigma), np.diag(shrunk.sigma)))
    off = corr[~np.eye(3, dtype=bool)]
    np.testing.assert_allclose(off, off[0], atol=1e-12)   # fully shrunk = constant corr
    assert off[0] == pytest.approx(shrunk.diagnostics["rho_bar"], abs=1e-12)


def test_shrinkage_preserves_variances():
    r = _rets()
    a = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.0)
    b = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.7)
    np.testing.assert_allclose(np.diag(a.sigma), np.diag(b.sigma), rtol=1e-10)


def test_pair_below_min_obs_falls_back_to_target_correlation():
    r = _rets(n=300)
    r.iloc[:-3, 2] = np.nan                       # C has only 3 usable observations
    out = ewma_covariance(r, halflife=63, min_obs=40, shrinkage=0.0)
    rho = out.diagnostics["rho_bar"]
    got = out.sigma.loc["A", "C"] / np.sqrt(
        out.sigma.loc["A", "A"] * out.sigma.loc["C", "C"])
    assert got == pytest.approx(rho, abs=1e-9)
    assert out.diagnostics["pairs_defaulted"] == 2   # (A,C) and (B,C)


def test_short_history_variance_floored_at_cross_sectional_median():
    r = _rets(n=300)
    r.iloc[:, 2] = np.nan
    r.iloc[-45:, 2] = 1e-8                        # near-zero-vol short history
    out = ewma_covariance(r, halflife=63, min_obs=40, shrinkage=0.0)
    med = float(np.median([out.sigma.loc["A", "A"], out.sigma.loc["B", "B"]]))
    assert out.sigma.loc["C", "C"] == pytest.approx(med)
    assert out.diagnostics["vars_floored"] == 1


def test_psd_repair_preserves_diagonal():
    from number7.risk.covariance import _psd_repair
    bad = pd.DataFrame([[1.0, 0.9, -0.9], [0.9, 1.0, 0.9], [-0.9, 0.9, 1.0]],
                       index=list("ABC"), columns=list("ABC"))
    fixed, clipped = _psd_repair(bad)             # infeasible triangle -> not PSD
    assert clipped
    np.testing.assert_allclose(np.diag(fixed), np.diag(bad), rtol=1e-10)
    assert np.linalg.eigvalsh(fixed.to_numpy()).min() >= -1e-12


def test_result_is_annualized():
    r = _rets()
    daily = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.0, ann_factor=1.0)
    ann = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.0)
    np.testing.assert_allclose(ann.sigma.to_numpy(), daily.sigma.to_numpy() * 252.0)


def test_empty_input_returns_empty_result():
    r = pd.DataFrame(index=pd.date_range("2025-01-01", periods=5, freq="B"))
    out = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.3)
    assert out.sigma.empty and out.corr.empty
