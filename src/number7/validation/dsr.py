from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()
_EULER = 0.5772156649015329


def psr(sr_obs: float, n_obs: int, skew: float, kurt: float,
        sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio (Bailey & Lopez de Prado). Per-period SR, KB-07 §4a."""
    if n_obs < 2:
        raise ValueError(f"psr requires n_obs >= 2, got {n_obs}")
    denom = math.sqrt(max(1.0 - skew * sr_obs + ((kurt - 1.0) / 4.0) * sr_obs ** 2, 1e-12))
    z = (sr_obs - sr_benchmark) * math.sqrt(n_obs - 1) / denom
    return _N.cdf(z)


def expected_max_sr(n_trials: int, var_trials: float) -> float:
    """E[max SR] under the null across K trials ('False Strategy' theorem, KB-07 §4a)."""
    k = max(int(n_trials), 1)
    if k == 1:
        return 0.0
    a = _N.inv_cdf(1.0 - 1.0 / k)
    b = _N.inv_cdf(1.0 - 1.0 / (k * math.e))
    return math.sqrt(max(var_trials, 0.0)) * ((1.0 - _EULER) * a + _EULER * b)


def dsr(sr_obs: float, n_obs: int, skew: float, kurt: float,
        n_trials: int, var_trials: float) -> float:
    """Deflated Sharpe Ratio: PSR against the data-mined expected-max hurdle.
    Passing = value ABOVE the hurdle from dsr_hurdle() (higher is better)."""
    return psr(sr_obs, n_obs, skew, kurt,
               sr_benchmark=expected_max_sr(n_trials, var_trials))


def dsr_hurdle(n_effective_trials: int, origin: str) -> float:
    """Blueprint §6 Gate 4 tiers: low-N uncertainty and LLM-originated families
    carry the stricter 0.98 hurdle."""
    if origin == "llm" or n_effective_trials < 15:
        return 0.98
    return 0.95
