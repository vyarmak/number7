"""EWMA covariance with the risk-layer spec §5 estimator contract.

Zero-mean EWMA (RiskMetrics convention) over the caller-supplied window; pairwise
complete-case with a min_obs fallback to the constant-correlation target; fixed-intensity
shrinkage (deliberately NOT Ledoit-Wolf optimal - a fitted intensity would be a searched
parameter); PSD repair that PRESERVES the diagonal (plain eigenvalue clipping silently
changes every name's variance)."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CovarianceResult:
    sigma: pd.DataFrame
    corr: pd.DataFrame
    diagnostics: dict


def _psd_repair(m: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Clip negative eigenvalues (eigh: m is symmetric), then restore the original
    diagonal by rescaling to correlation form and rebuilding with the pre-clip
    variances (spec §5)."""
    vals, vecs = np.linalg.eigh(m.to_numpy())
    if vals.min() >= -1e-12:
        return m, False
    rebuilt = vecs @ np.diag(np.clip(vals, 0.0, None)) @ vecs.T
    d = np.sqrt(np.clip(np.diag(rebuilt), 1e-30, None))
    corr = rebuilt / np.outer(d, d)
    np.fill_diagonal(corr, 1.0)
    orig = np.sqrt(np.diag(m.to_numpy()))
    out = corr * np.outer(orig, orig)
    return pd.DataFrame(out, index=m.index, columns=m.columns), True


def ewma_covariance(rets: pd.DataFrame, *, halflife: int, min_obs: int,
                    shrinkage: float, ann_factor: float = 252.0) -> CovarianceResult:
    cols = rets.columns
    k = len(cols)
    if k == 0:
        empty = pd.DataFrame(index=cols, columns=cols, dtype=float)
        return CovarianceResult(sigma=empty, corr=empty.copy(),
                                diagnostics={"psd_clipped": False, "pairs_defaulted": 0,
                                             "vars_floored": 0, "rho_bar": 0.0})
    n = len(rets)
    x = rets.to_numpy(dtype=float)
    present = np.isfinite(x)
    xf = np.where(present, x, 0.0)
    w = 0.5 ** (np.arange(n - 1, -1, -1, dtype=float) / halflife)

    # pairwise EWMA second moments: cov_jk = sum_t w_t x_tj x_tk [both present]
    #                                       / sum_t w_t [both present]
    num = (xf * w[:, None]).T @ xf
    den = (present * w[:, None]).T @ present.astype(float)
    counts = present.T.astype(int) @ present.astype(int)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = num / den

    # variance floor (spec §5): short-history names get at least the cross-sectional
    # median variance of the fullest-history names (a name must not set its own floor)
    var = np.diag(cov).copy()
    obs = counts.diagonal()
    fullest = obs == obs.max()
    finite = np.isfinite(var) & (var > 0)
    ref = var[fullest & finite]
    med = float(np.median(ref)) if len(ref) else 0.0
    short = obs < n
    to_floor = (short & (var < med)) | ~finite
    var = np.where(to_floor, med, var)

    d = np.sqrt(np.clip(var, 1e-30, None))
    with np.errstate(invalid="ignore", divide="ignore"):
        corr = cov / np.outer(np.sqrt(np.clip(np.diag(cov), 1e-30, None)),
                              np.sqrt(np.clip(np.diag(cov), 1e-30, None)))
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1.0, 1.0)

    # rho_bar from pairs with enough overlap, clipped so the target itself is PSD
    iu = np.triu_indices(k, 1)
    ok = counts[iu] >= min_obs
    valid = np.isfinite(corr[iu]) & ok
    rho_bar = float(np.mean(corr[iu][valid])) if valid.any() else 0.0
    rho_bar = float(np.clip(rho_bar, -1.0 / max(k - 1, 1), 1.0))

    # pairs below min_obs (or non-finite): fall back to the target correlation
    bad_pair = (counts < min_obs) | ~np.isfinite(corr)
    np.fill_diagonal(bad_pair, False)
    pairs_defaulted = int(bad_pair[iu].sum())
    corr = np.where(bad_pair, rho_bar, corr)

    target = np.full((k, k), rho_bar)
    np.fill_diagonal(target, 1.0)
    shrunk_corr = (1.0 - shrinkage) * corr + shrinkage * target
    sigma = shrunk_corr * np.outer(d, d)

    sigma_df = pd.DataFrame(sigma, index=cols, columns=cols)
    sigma_df, clipped = _psd_repair(sigma_df)
    return CovarianceResult(
        sigma=sigma_df * ann_factor,
        corr=pd.DataFrame(corr, index=cols, columns=cols),
        diagnostics={"psd_clipped": clipped, "pairs_defaulted": pairs_defaulted,
                     "vars_floored": int(to_floor.sum()), "rho_bar": rho_bar},
    )
