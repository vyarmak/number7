from __future__ import annotations

import numpy as np


def _max_dd(log_rets: np.ndarray) -> float:
    eq = np.exp(np.cumsum(log_rets))
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


def block_bootstrap_dd(daily_log_returns, block: int = 10, n: int = 2000,
                       seed: int = 0) -> dict:
    """Block bootstrap (autocorrelation-respecting) drawdown bands and Sharpe CI —
    feeds blueprint Gate 2/5 and the §8 brake calibration."""
    r = np.asarray(daily_log_returns, dtype=float)
    rng = np.random.default_rng(seed)
    length = len(r)
    dds, sharpes = [], []
    n_starts = max(length - block + 1, 1)          # inclusive of the final valid start
    for _ in range(n):
        idx: list[int] = []
        while len(idx) < length:
            s = int(rng.integers(0, n_starts))
            idx.extend(range(s, min(s + block, length)))
        path = r[np.array(idx[:length])]
        dds.append(_max_dd(path))
        sharpes.append(float(path.mean() / (path.std(ddof=0) or 1e-12) * np.sqrt(252)))
    dds_a, sharpes_a = np.array(dds), np.array(sharpes)
    return {"dd_p95": float(np.quantile(dds_a, 0.05)),
            "dd_p99": float(np.quantile(dds_a, 0.01)),
            "sharpe_ci90": (float(np.quantile(sharpes_a, 0.05)),
                            float(np.quantile(sharpes_a, 0.95)))}
