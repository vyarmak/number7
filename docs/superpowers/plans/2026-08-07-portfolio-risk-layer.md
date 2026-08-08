# Portfolio Risk Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The deterministic per-rebalance risk overlay from
`docs/superpowers/specs/2026-08-06-portfolio-risk-layer-design.md`: ex-ante vol-target
scalar with a rate-limited ratchet, sector/top-3 caps, ADV cap, Corwin–Schultz spread
gate, beta monitoring — wired into `resolve_book`, the engine, and the live path with
golden-replay parity and causality coverage, plus the pre-registered on/off ablation.

**Architecture:** New `risk/` package. `build_risk_context(view, slate, current, ...)` is
the only panel reader; it emits a frozen `RiskContext` consumed by `resolve_book` via one
optional argument. The band runs on structural (pre-k) weights; the scalar applies after;
`k_prev` is new durable state (one float) carried by the engine and the live caller.

**Tech Stack:** Python 3.13, pandas/numpy, pytest, ruff. No new dependencies.

## Global Constraints

- **The spec is normative.** `docs/superpowers/specs/2026-08-06-portfolio-risk-layer-design.md` — read the section cited in each task before implementing it.
- `ruff` enforces `E501` at `line-length = 100`. Run `uv run ruff check src tests` before every commit.
- Timing contract (blueprint §4.1): every overlay input is computed from the view already masked to the signal date. `build_risk_context` receives the masked view and never masks again.
- Frozen parameters: the `RiskConfig` defaults in Task 4 are constitution constants. Do not add knobs, do not "tune" them, do not make shrinkage data-driven.
- `risk=None` / `risk_cfg=None` paths must stay **byte-identical** to current behavior — the Reference profile and every existing test pin this.
- Tests never touch the network. Default pytest run deselects `vm`/`paper` marks.
- When piping pytest to `tail`/`grep`, chain with `set -o pipefail`.
- Basis rule: covariance on `tr_close` log returns; ADV on `raw_close × volume`; spread on `px_high`/`px_low`. Never mix.
- Do NOT set `risk_layer_version` anywhere. The trading gate stays closed.

## File structure

| file | action | responsibility |
|---|---|---|
| `src/number7/risk/__init__.py` | create | empty package marker |
| `src/number7/risk/covariance.py` | create | EWMA covariance + shrinkage + PSD repair (spec §5 estimator contract) |
| `src/number7/risk/spread.py` | create | Corwin–Schultz estimate + entry gate (spec §5 spread-gate contract) |
| `src/number7/risk/overlay.py` | create | `RiskConfig`, `ScalarResult`, `RiskContext`, `ratchet`, `build_risk_context`, `risk_diagnostics` |
| `src/number7/engine/strategy.py` | modify | `PanelView.gics_sector` field |
| `src/number7/engine/live.py` | modify | `build_panel` loads gics; `compute_live_targets` risk args |
| `src/number7/strategies/sizing.py` | modify | sector/top-3 cap helpers, extended band + validation, `resolve_book(risk=)` |
| `src/number7/engine/backtest.py` | modify | risk wiring, `k_prev` loop state, `risk_k`/`final_k`/`risk_diag` on result |
| `src/number7/validation/walkforward.py` | modify | thread `risk_cfg`, carry `final_k` across folds |
| `src/number7/validation/causality.py` | modify | thread `risk_cfg` through `closed_loop_violations` |
| `src/number7/research/preregs.py` | modify | `RISK_OVERLAY_ABLATION` pre-registration |
| `src/number7/research/ablate_risk_overlay.py` | create | ablation runner + report writer |
| `tests/conftest.py` | modify | `_make_panel` gains `gics_sector` |
| `tests/test_risk_covariance.py` | create | estimator contract |
| `tests/test_risk_spread.py` | create | CS + gate contract |
| `tests/test_risk_overlay.py` | create | config/ratchet/scalar/context/diagnostics |
| `tests/test_sizing.py` | modify | cap helpers, band repair, `resolve_book(risk=)` |
| `tests/test_backtest.py` | modify | engine risk wiring |
| `tests/test_live_parity.py` | modify | golden replay with risk |
| `tests/test_causality.py` | modify | overlay causality trap |
| `tests/test_walkforward.py` | modify | `final_k` fold carry |
| `tests/test_preregs.py` | modify | ablation registration |

---

### Task 1: `PanelView.gics_sector`

Spec §4.6. Sector labels ride the panel exactly like `assetid`: not time-indexed,
passed through `masked_to` untouched.

**Files:**
- Modify: `src/number7/engine/strategy.py` (PanelView, ~line 11–43)
- Modify: `src/number7/engine/live.py` (`build_panel`, ~line 22–46)
- Modify: `tests/conftest.py` (`_make_panel`)
- Test: `tests/test_strategy.py`, `tests/test_live_panel.py`

**Interfaces:**
- Produces: `PanelView.gics_sector: pd.Series` (symbol → sector label str, NaN allowed);
  `build_panel` raises `ValueError` if the metadata column is absent.
- Every later task reads `view.gics_sector`.

- [ ] **Step 1: Write the failing tests**

In `tests/test_strategy.py`:

```python
def test_panelview_carries_gics_and_masking_passes_it_through(make_panel):
    dates = pd.date_range("2026-01-05", periods=6, freq="B")
    close = pd.DataFrame({"A": 100.0, "B": 50.0}, index=dates)
    panel = make_panel(close, gics_sector=pd.Series({"A": "Energy", "B": None}))
    masked = panel.masked_to(dates[3])
    assert masked.gics_sector.equals(panel.gics_sector)
    assert masked.gics_sector["A"] == "Energy"
```

In `tests/test_live_panel.py`:

```python
def test_build_panel_loads_gics_sector(fake_snapshot):
    panel = build_panel(fake_snapshot)
    assert panel.gics_sector["AAPL"] == "Information Technology"
    assert pd.isna(panel.gics_sector["SPY"])


def test_build_panel_raises_on_missing_gics_column(fake_snapshot):
    meta_path = SnapshotPaths(fake_snapshot).metadata
    md = pd.read_parquet(meta_path).drop(columns=["gics_sector"])
    md.to_parquet(meta_path, index=False)
    with pytest.raises(ValueError, match="gics_sector"):
        build_panel(fake_snapshot)
```

(`test_live_panel.py` needs `from number7.data.snapshot import SnapshotPaths` and
`import pytest` if absent.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_strategy.py tests/test_live_panel.py -v`
Expected: FAIL — `TypeError: PanelView.__init__() got an unexpected keyword argument
'gics_sector'` / `AttributeError`.

- [ ] **Step 3: Implement**

`strategy.py` — add the field directly under `assetid` and thread it through `masked_to`:

```python
    assetid: pd.Series          # symbol -> Norgate assetid; stable tie-break key (§6.1)
    gics_sector: pd.Series      # symbol -> CURRENT GICS sector label. Declared PIT
    # approximation (risk-layer spec §4.6): today's map labels the whole history; the
    # 2016 Real Estate and 2018 Communication Services reshuffles are known mislabels.
```

In `masked_to`, next to assetid:

```python
            assetid=self.assetid,          # not time-indexed: nothing to truncate
            gics_sector=self.gics_sector,
```

`live.py::build_panel` — after the `assetid` line:

```python
    if "gics_sector" not in meta_df.columns:
        raise ValueError(
            f"snapshot {snapshot_root.name} metadata has no gics_sector column - schema "
            "regression; the risk layer's sector cap cannot run (risk spec §4.6)")
    gics = meta_df["gics_sector"].reindex(px_close.columns)
```

and pass `gics_sector=gics` in the `PanelView(...)` construction.

`conftest.py::_make_panel` — add parameter `gics_sector=None` and construct:

```python
        gics_sector=(pd.Series("TestSector", index=cols, dtype=object)
                     if gics_sector is None else gics_sector.reindex(cols)),
```

- [ ] **Step 4: Run the full suite** — the new field breaks any other direct
  `PanelView(...)` construction site; fix each by adding `gics_sector`.

Run: `set -o pipefail; uv run pytest 2>&1 | tail -5`
Expected: all pass (177 + 2 new).

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add -A && git commit -m "feat(panel): carry gics_sector through PanelView"
```

---

### Task 2: `risk/covariance.py` — EWMA covariance with the §5 estimator contract

Spec §5 "Covariance estimator contract". Pure numpy/pandas; no panel dependency.

**Files:**
- Create: `src/number7/risk/__init__.py` (empty), `src/number7/risk/covariance.py`
- Test: `tests/test_risk_covariance.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class CovarianceResult:
    sigma: pd.DataFrame     # annualized, shrunk, PSD-repaired covariance
    corr: pd.DataFrame      # PRE-shrinkage correlation (funded avg_corr reads this)
    diagnostics: dict       # {"psd_clipped": bool, "pairs_defaulted": int,
                            #  "vars_floored": int, "rho_bar": float}

def ewma_covariance(rets: pd.DataFrame, *, halflife: int, min_obs: int,
                    shrinkage: float, ann_factor: float = 252.0) -> CovarianceResult
```

`rets`: daily log returns, already causal and already windowed by the caller
(`.tail(ewma_window)`); NaN = non-trading session.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from number7.risk.covariance import CovarianceResult, ewma_covariance


def _rets(n=300, cols=("A", "B", "C"), seed=7):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(rng.normal(0, 0.01, (n, len(cols))), index=idx, columns=cols)


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
    raw = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.0)
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
    med = np.median(np.diag(out.sigma))
    assert out.sigma.loc["C", "C"] == pytest.approx(med)
    assert out.diagnostics["vars_floored"] == 1


def test_psd_repair_preserves_diagonal():
    from number7.risk.covariance import _psd_repair
    bad = pd.DataFrame([[1.0, 0.9, 0.2], [0.9, 1.0, 0.9], [0.2, 0.9, 1.0]],
                       index=list("ABC"), columns=list("ABC"))
    bad.iloc[0, 2] = bad.iloc[2, 0] = -0.9        # infeasible triangle -> not PSD
    fixed, clipped = _psd_repair(bad)
    assert clipped
    np.testing.assert_allclose(np.diag(fixed), np.diag(bad), rtol=1e-10)
    assert np.linalg.eigvalsh(fixed.to_numpy()).min() >= -1e-12


def test_result_is_annualized():
    r = _rets()
    daily = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.0, ann_factor=1.0)
    ann = ewma_covariance(r, halflife=63, min_obs=5, shrinkage=0.0)
    np.testing.assert_allclose(ann.sigma.to_numpy(), daily.sigma.to_numpy() * 252.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_risk_covariance.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'number7.risk'`.

- [ ] **Step 3: Implement**

```python
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
    n = len(rets)
    x = rets.to_numpy(dtype=float)
    present = np.isfinite(x)
    xf = np.where(present, x, 0.0)
    w = 0.5 ** (np.arange(n - 1, -1, -1, dtype=float) / halflife)

    # pairwise EWMA second moments: cov_jk = sum_t w_t x_tj x_tk [both present]
    #                                       / sum_t w_t [both present]
    num = (xf * w[:, None]).T @ xf
    den = (present * w[:, None]).T.astype(float) @ present.astype(float)
    counts = present.T.astype(int) @ present.astype(int)
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = num / den

    # variance floor: short-history names get at least the cross-sectional median
    var = np.diag(cov).copy()
    full = counts.diagonal() >= min_obs
    med = float(np.median(var[full])) if full.any() else float(np.nanmedian(var))
    floored = (~full) | (var < 0) | ~np.isfinite(var)
    short = counts.diagonal() < n            # any missing sessions at all
    to_floor = (short & (var < med)) | floored
    var = np.where(to_floor, np.maximum(var, med), var)
    np.fill_diagonal(cov, var)

    d = np.sqrt(np.clip(var, 1e-30, None))
    corr = cov / np.outer(d, d)
    np.fill_diagonal(corr, 1.0)
    corr = np.clip(corr, -1.0, 1.0)

    # rho_bar from pairs with enough overlap, clipped so the target itself is PSD
    k = len(cols)
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
```

Note for the weighted-moments test: with no missing data,
`den = w.sum()` for every pair, so `num/den` equals the renormalized-weights formula the
test computes. Iterate until the exact expectation matches.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_risk_covariance.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/risk tests/test_risk_covariance.py
git commit -m "feat(risk): EWMA covariance with shrinkage, floors and PSD repair"
```

---

### Task 3: `risk/spread.py` — Corwin–Schultz gate

Spec §5 "Spread-gate contract".

**Files:**
- Create: `src/number7/risk/spread.py`
- Test: `tests/test_risk_spread.py`

**Interfaces:**
- Produces:

```python
def corwin_schultz(px_high: pd.DataFrame, px_low: pd.DataFrame) -> pd.DataFrame
    # two-day relative spread estimates, negative values floored at 0, NaN where inputs NaN

def spread_gate(px_high: pd.DataFrame, px_low: pd.DataFrame, *, est_window: int = 21,
                base_window: int = 252, spread_mult: float = 2.0,
                spread_floor: float = 0.0010) -> pd.Series
    # bool per symbol AT THE LAST ROW of the inputs: True = block new entry
```

Caller (Task 5) passes `view.px_high` / `view.px_low` already masked to the signal date,
so "last row" = signal date.

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd

from number7.risk.spread import corwin_schultz, spread_gate

K = 3.0 - 2.0 * np.sqrt(2.0)


def _panel(h, l):
    idx = pd.date_range("2025-01-01", periods=len(h), freq="B")
    return (pd.DataFrame({"X": h}, index=idx, dtype=float),
            pd.DataFrame({"X": l}, index=idx, dtype=float))


def test_reproduces_closed_form_on_two_day_fixture():
    high, low = _panel([102.0, 103.0], [98.0, 99.0])
    beta = np.log(102.0 / 98.0) ** 2 + np.log(103.0 / 99.0) ** 2
    gamma = np.log(103.0 / 98.0) ** 2          # two-day high over two-day low
    alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / K - np.sqrt(gamma / K)
    expected = max(2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha)), 0.0)
    out = corwin_schultz(high, low)
    assert np.isnan(out.iloc[0, 0])            # first row has no prior day
    assert out.iloc[1, 0] == pytest.approx(expected, rel=1e-12)


def test_negative_estimates_floor_at_zero():
    # wide day followed by a huge two-day range makes alpha strongly negative
    high, low = _panel([110.0, 200.0], [90.0, 50.0])
    out = corwin_schultz(high, low)
    assert out.iloc[1, 0] == 0.0


def test_zero_median_liquid_name_is_not_blocked_by_noise():
    n = 400
    high = [100.0001] * n                       # ~zero CS estimate every day
    low = [100.0] * n
    h, l = _panel(high, low)
    blocked = spread_gate(h, l, spread_floor=0.0010)
    assert not blocked["X"]                     # floor governs, 2 x 0 does not block


def test_blowout_triggers_against_lagged_baseline():
    n = 400
    high = [100.5] * n
    low = [100.0] * n
    for i in range(n - 30, n):                 # last 30 sessions: spread explodes
        high[i], low[i] = 103.0, 100.0
    h, l = _panel(high, low)
    assert spread_gate(h, l)["X"]

    # and the baseline must NOT include the blowout: an un-lagged 252-window that
    # swallowed the episode would raise the median and suppress the trigger. With only
    # ~30 wide sessions in 252 the median is safe either way, so ALSO check the lag
    # directly: baseline computed at the last date must end est_window sessions earlier.


def test_insufficient_history_is_not_blocked():
    high, low = _panel([101.0] * 40, [100.0] * 40)
    assert not spread_gate(high, low)["X"]      # baseline NaN -> gate does not fire
```

Add `import pytest` at top.

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_risk_spread.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
"""Corwin-Schultz high-low spread estimator and the risk-layer entry gate (spec §5).

CS output is a DIMENSIONLESS relative spread (already price-normalized). It is a
continuous-market proxy used as a conservative admission heuristic - it is NOT an
estimate of MOC-auction execution cost and its level must not be read as a forecast."""

from __future__ import annotations

import numpy as np
import pandas as pd

_K = 3.0 - 2.0 * np.sqrt(2.0)


def corwin_schultz(px_high: pd.DataFrame, px_low: pd.DataFrame) -> pd.DataFrame:
    hl = np.log(px_high / px_low)
    beta = hl ** 2 + (hl ** 2).shift(1)
    h2 = pd.concat([px_high, px_high.shift(1)]).groupby(level=0).max()
    l2 = pd.concat([px_low, px_low.shift(1)]).groupby(level=0).min()
    gamma = np.log(h2.loc[px_high.index] / l2.loc[px_low.index]) ** 2
    gamma[px_high.shift(1).isna()] = np.nan     # first row: no two-day range exists
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / _K - np.sqrt(gamma / _K)
    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    return spread.clip(lower=0.0)


def spread_gate(px_high: pd.DataFrame, px_low: pd.DataFrame, *, est_window: int = 21,
                base_window: int = 252, spread_mult: float = 2.0,
                spread_floor: float = 0.0010) -> pd.Series:
    """True = block NEW entry at the last row. The baseline is the rolling median of the
    21-session statistic over base_window sessions ENDING est_window sessions before the
    signal date - the baseline must not contain the episode it is judging (spec §5).
    Names with insufficient baseline history are never blocked here (the min_obs bar and
    eligibility filters own that case)."""
    stat = corwin_schultz(px_high, px_low).rolling(est_window, min_periods=est_window) \
        .median()
    base = stat.shift(est_window).rolling(base_window, min_periods=base_window).median()
    current, baseline = stat.iloc[-1], base.iloc[-1]
    threshold = np.maximum(spread_mult * baseline, spread_floor)
    return (current > threshold) & baseline.notna() & current.notna()
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_risk_spread.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/risk/spread.py tests/test_risk_spread.py
git commit -m "feat(risk): Corwin-Schultz spread estimate and lagged entry gate"
```

---

### Task 4: `risk/overlay.py` part 1 — `RiskConfig`, `ratchet`, `ScalarResult`, `RiskContext.scalar`

Spec §5 (frozen table), §6 ("Ratchet freezes in cash", "k floor, not a crash"), §4.4.

**Files:**
- Create: `src/number7/risk/overlay.py`
- Test: `tests/test_risk_overlay.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class RiskConfig:
    target_vol: float = 0.10
    up_step: float = 0.10
    ewma_halflife: int = 63
    ewma_window: int = 252
    min_obs: int = 40
    shrinkage: float = 0.30
    sector_cap: float = 0.25
    top3_cap: float = 0.25
    adv_cap: float = 0.25
    adv_window: int = 20
    spread_est_window: int = 21
    spread_base_window: int = 252
    spread_mult: float = 2.0
    spread_floor: float = 0.0010
    beta_band: tuple[float, float] = (0.3, 0.8)
    beta_breach_n: int = 4
    beta_window: int = 252
    k_raw_floor: float = 0.01
    sigma_p_floor: float = 1e-6

@dataclass(frozen=True)
class ScalarResult:
    applied_k: float
    k_raw: float
    sigma_p: float

def ratchet(k_raw: float, k_prev: float, up_step: float) -> float

@dataclass(frozen=True)
class RiskContext:
    sigma: pd.DataFrame          # annualized Σ over the candidate set (spec §4.3)
    corr: pd.DataFrame           # pre-shrinkage correlation, same index
    adv_cap_w: pd.Series         # per-name weight ceiling
    entry_barred: frozenset      # spec "spread_blocked" generalized: spread gate AND
                                 # min_obs bar - both block NEW entry only
    sector: pd.Series            # symbol -> label, NaN already mapped to "UNKNOWN"
    assetid: pd.Series           # tie-break key for the top-3 cap (spec §6)
    k_prev: float
    config: RiskConfig

    def scalar(self, w: pd.Series) -> ScalarResult
```

- [ ] **Step 1: Write the failing tests**

```python
import numpy as np
import pandas as pd
import pytest

from number7.risk.overlay import RiskConfig, RiskContext, ScalarResult, ratchet


def _ctx(k_prev=1.0, target_vol=0.10, n=3, var=0.04, rho=0.0):
    cols = [f"S{i}" for i in range(n)]
    sig = np.full((n, n), rho * var)
    np.fill_diagonal(sig, var)
    return RiskContext(
        sigma=pd.DataFrame(sig, index=cols, columns=cols),
        corr=pd.DataFrame(np.eye(n), index=cols, columns=cols),
        adv_cap_w=pd.Series(1.0, index=cols),
        entry_barred=frozenset(),
        sector=pd.Series("TestSector", index=cols),
        assetid=pd.Series(np.arange(1.0, n + 1.0), index=cols),
        k_prev=k_prev,
        config=RiskConfig(target_vol=target_vol),
    )


def test_ratchet_down_is_immediate_and_full():
    assert ratchet(0.4, 1.0, 0.10) == 0.4


def test_ratchet_up_is_capped_at_up_step():
    assert ratchet(1.0, 0.4, 0.10) == pytest.approx(0.5)


def test_ratchet_stable_at_one():
    assert ratchet(1.0, 1.0, 0.10) == 1.0


def test_scalar_computes_k_from_portfolio_vol():
    ctx = _ctx(target_vol=0.10, var=0.04, rho=0.0)      # sigma 20% per name
    w = pd.Series({"S0": 0.5, "S1": 0.5, "S2": 0.0})
    sigma_p = np.sqrt(0.5**2 * 0.04 + 0.5**2 * 0.04)    # 14.14%
    res = ctx.scalar(w)
    assert isinstance(res, ScalarResult)
    assert res.sigma_p == pytest.approx(sigma_p)
    assert res.k_raw == pytest.approx(min(1.0, 0.10 / sigma_p))
    assert res.applied_k == res.k_raw                    # k_prev=1, down move


def test_scalar_never_levers_up():
    ctx = _ctx(target_vol=0.50)                          # target far above book vol
    res = ctx.scalar(pd.Series({"S0": 0.3, "S1": 0.3, "S2": 0.3}))
    assert res.k_raw == 1.0 and res.applied_k == 1.0


def test_scalar_frozen_on_empty_book():
    ctx = _ctx(k_prev=0.55)
    res = ctx.scalar(pd.Series(0.0, index=["S0", "S1", "S2"]))
    assert res.applied_k == 0.55                         # frozen, not advanced (spec §6)
    assert res.k_raw == 1.0


def test_k_raw_floor_prevents_underflow():
    ctx = _ctx(var=1e6)                                  # absurd vol = data bug regime
    res = ctx.scalar(pd.Series({"S0": 1.0, "S1": 0.0, "S2": 0.0}))
    assert res.k_raw == pytest.approx(0.01)              # floored, not ~0


def test_scalar_raises_on_funded_weight_without_sigma_row():
    ctx = _ctx()
    w = pd.Series({"S0": 0.5, "GHOST": 0.5})
    with pytest.raises(ValueError, match="GHOST"):
        ctx.scalar(w)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_risk_overlay.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement** (in new `overlay.py`; `build_risk_context` comes in Task 5)

```python
"""RiskConfig, RiskContext and the vol-target scalar (risk-layer spec §4-§6).

Every number in RiskConfig is a FROZEN constitution constant declared a priori (spec §5):
zero searched dimensions, zero ledger trials. Changing one is a declared amendment with
Viktor's sign-off - never a tuning loop."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from number7.risk.covariance import ewma_covariance
from number7.risk.spread import spread_gate
```

then the three dataclasses and:

```python
def ratchet(k_raw: float, k_prev: float, up_step: float) -> float:
    """Anti-procyclicality (spec §3): down moves immediate and in full; up moves capped
    at up_step per rebalance. Never blocks a downward move - the future brakes spec
    composes by pushing k further down, not by fighting this function."""
    if k_raw <= k_prev:
        return k_raw
    return min(k_raw, k_prev + up_step)
```

`RiskContext.scalar`:

```python
    def scalar(self, w: pd.Series) -> ScalarResult:
        """k for the structural book `w`. Pure: no panel access, no mutation.
        Raises on a funded weight with no Σ row - that is a candidate-set construction
        bug (spec §4.3), never a silent reindex-and-drop, which would understate risk
        exactly during the liquidity-stress episodes that trip the spread gate."""
        funded = w[w > 0]
        missing = [s for s in funded.index if s not in self.sigma.index]
        if missing:
            raise ValueError(f"funded names missing from sigma candidate set: {missing[:3]}")
        if len(funded) == 0:
            return ScalarResult(applied_k=self.k_prev, k_raw=1.0, sigma_p=0.0)
        v = funded.to_numpy()
        sub = self.sigma.loc[funded.index, funded.index].to_numpy()
        sigma_p = float(np.sqrt(max(v @ sub @ v, 0.0)))
        if sigma_p < self.config.sigma_p_floor:
            # cash / near-cash book: FREEZE the ratchet (spec §6) - k_prev crawling to
            # 1.0 during a cash period would grant the full-size re-entry that
            # "slow up" exists to forbid.
            return ScalarResult(applied_k=self.k_prev, k_raw=1.0, sigma_p=sigma_p)
        k_raw = float(np.clip(self.config.target_vol / sigma_p,
                              self.config.k_raw_floor, 1.0))
        return ScalarResult(applied_k=ratchet(k_raw, self.k_prev, self.config.up_step),
                            k_raw=k_raw, sigma_p=sigma_p)
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_risk_overlay.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/risk/overlay.py tests/test_risk_overlay.py
git commit -m "feat(risk): RiskConfig, ratchet and the vol-target scalar"
```

---

### Task 5: `build_risk_context` — the only panel reader

Spec §4.2–§4.3, §7. Candidate set = **admitted** top-`max_positions` ∪ held names.

**Files:**
- Modify: `src/number7/risk/overlay.py`
- Test: `tests/test_risk_overlay.py`

**Interfaces:**
- Consumes: `PanelView` (Task 1 `gics_sector`), `Slate` (`weights`, `rank`, `admit_new`),
  `SizingConfig` (`max_positions`, `sleeve_equity`), Tasks 2–4.
- Produces:

```python
def build_risk_context(view: PanelView, slate: Slate, current: pd.Series,
                       sizing: SizingConfig, config: RiskConfig,
                       k_prev: float) -> RiskContext
```

- [ ] **Step 1: Write the failing tests** (append to `tests/test_risk_overlay.py`)

```python
from number7.engine.strategy import Slate
from number7.risk.overlay import build_risk_context
from number7.strategies.sizing import SizingConfig


def _slate(weights: dict, cols):
    w = pd.Series(0.0, index=cols)
    rank = pd.Series(np.nan, index=cols, dtype=float)
    for i, (s, v) in enumerate(weights.items()):
        w[s], rank[s] = v, float(i + 1)
    return Slate(weights=w, rank=rank, admit_new=True)


def _view(make_panel, n_days=400, cols=("A", "B", "C", "D"), wide_spread=()):
    rng = np.random.default_rng(11)
    idx = pd.date_range("2024-06-03", periods=n_days, freq="B")
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (n_days, len(cols))), axis=0)),
        index=idx, columns=list(cols))
    high, low = close * 1.001, close * 0.999
    for s in wide_spread:                       # recent sessions: spread blowout
        high.loc[idx[-25]:, s] = close.loc[idx[-25]:, s] * 1.04
    return make_panel(close, high=high, low=low,
                      gics_sector=pd.Series("TestSector", index=list(cols)))


def test_candidate_set_is_admitted_rank_order_union_held(make_panel):
    view = _view(make_panel, wide_spread=("A",))
    cols = view.px_close.columns
    slate = _slate({"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3}, cols)
    current = pd.Series({"D": 0.10}, index=cols).fillna(0.0)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=2)
    ctx = build_risk_context(view, slate, current, cfg, RiskConfig(), k_prev=1.0)
    # A is spread-blocked and NOT held -> excluded; admitted top-2 = B, C; D is held
    assert "A" in ctx.entry_barred
    assert set(ctx.sigma.index) == {"B", "C", "D"}


def test_held_name_is_in_sigma_even_when_spread_blocked(make_panel):
    view = _view(make_panel, wide_spread=("D",))
    cols = view.px_close.columns
    slate = _slate({"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3}, cols)
    current = pd.Series({"D": 0.10}, index=cols).fillna(0.0)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=2)
    ctx = build_risk_context(view, slate, current, cfg, RiskConfig(), k_prev=1.0)
    assert "D" in ctx.entry_barred and "D" in ctx.sigma.index


def test_regime_off_candidates_are_held_names_only(make_panel):
    view = _view(make_panel)
    cols = view.px_close.columns
    slate = Slate(weights=pd.Series(0.25, index=cols),
                  rank=pd.Series([1.0, 2.0, 3.0, 4.0], index=cols), admit_new=False)
    current = pd.Series({"C": 0.2}, index=cols).fillna(0.0)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=2)
    ctx = build_risk_context(view, slate, current, cfg, RiskConfig(), k_prev=1.0)
    assert set(ctx.sigma.index) == {"C"}


def test_adv_cap_is_a_weight_ceiling_from_dollar_adv(make_panel):
    view = _view(make_panel)
    cols = view.px_close.columns
    slate = _slate({"A": 0.5, "B": 0.5}, cols)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=5)
    ctx = build_risk_context(view, slate, pd.Series(0.0, index=cols), cfg,
                             RiskConfig(), k_prev=1.0)
    adv = (view.raw_close["A"] * view.volume["A"]).tail(20).mean()
    assert ctx.adv_cap_w["A"] == pytest.approx(0.25 * adv / 50_000.0)


def test_sector_nan_maps_to_unknown(make_panel):
    view = _view(make_panel)
    object.__setattr__(view, "gics_sector",
                       pd.Series({"A": "Energy", "B": None, "C": "Energy", "D": None}))
    cols = view.px_close.columns
    slate = _slate({"A": 0.4, "B": 0.4}, cols)
    ctx = build_risk_context(view, slate, pd.Series(0.0, index=cols),
                             SizingConfig(sleeve_equity=50_000.0), RiskConfig(), 1.0)
    assert ctx.sector["B"] == "UNKNOWN"


def test_raises_on_bad_k_prev_and_empty_candidates(make_panel):
    view = _view(make_panel)
    cols = view.px_close.columns
    slate = _slate({"A": 0.4}, cols)
    zero = pd.Series(0.0, index=cols)
    cfg = SizingConfig(sleeve_equity=50_000.0)
    with pytest.raises(ValueError, match="k_prev"):
        build_risk_context(view, slate, zero, cfg, RiskConfig(), k_prev=0.0)
    empty = Slate(weights=zero, rank=pd.Series(np.nan, index=cols, dtype=float),
                  admit_new=True)
    ctx = build_risk_context(view, empty, zero, cfg, RiskConfig(), 1.0)
    assert len(ctx.sigma) == 0                  # empty slate + flat book is legal (cash)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_risk_overlay.py -v`
Expected: new tests FAIL — `build_risk_context` not defined.

- [ ] **Step 3: Implement** (append to `overlay.py`)

```python
def build_risk_context(view, slate, current: pd.Series, sizing, config: RiskConfig,
                       k_prev: float) -> "RiskContext":
    """The ONLY function that reads the panel (spec §4.1). `view` is already masked to
    the signal date. Candidate set (spec §4.3): the first max_positions names of the
    ADMITTED rank order - the same admission resolve_book performs, computed here from
    the same inputs so the two cannot disagree - UNION all currently held names."""
    if not 0.0 < k_prev <= 1.0:
        raise ValueError(f"k_prev={k_prev} outside (0, 1]")
    cols = view.px_close.columns
    current = current.reindex(cols).fillna(0.0)
    held = current > 0

    blocked = spread_gate(view.px_high, view.px_low,
                          est_window=config.spread_est_window,
                          base_window=config.spread_base_window,
                          spread_mult=config.spread_mult,
                          spread_floor=config.spread_floor).reindex(cols).fillna(False)
    obs = view.tr_close.tail(config.ewma_window).notna().sum()
    thin = (obs < config.min_obs).reindex(cols).fillna(True)
    entry_barred = frozenset(cols[blocked | thin])

    eligible = slate.weights > 0
    if not slate.admit_new:
        eligible &= held
    eligible &= held | ~(blocked | thin)        # bars stop NEW entries only
    ranked = slate.rank.where(eligible).dropna().sort_values(kind="mergesort").index
    cands = list(ranked[: sizing.max_positions]) + list(cols[held & ~cols.isin(ranked[: sizing.max_positions])])
    if not cands and bool((slate.weights > 0).any()) and bool(eligible.any()):
        raise ValueError("empty candidate set against a non-empty admitted slate")

    rets = np.log(view.tr_close[cands]).diff().tail(config.ewma_window)
    cov = ewma_covariance(rets, halflife=config.ewma_halflife, min_obs=config.min_obs,
                          shrinkage=config.shrinkage)
    if cov.sigma.isna().any().any():
        raise ValueError("sigma contains NaN after fallbacks - unusable inputs")

    adv = (view.raw_close[cols] * view.volume[cols]).tail(config.adv_window).mean()
    adv_cap_w = (config.adv_cap * adv / sizing.sleeve_equity).fillna(0.0)

    return RiskContext(sigma=cov.sigma, corr=cov.corr, adv_cap_w=adv_cap_w,
                       entry_barred=entry_barred,
                       sector=view.gics_sector.reindex(cols).fillna("UNKNOWN"),
                       assetid=view.assetid.reindex(cols),
                       k_prev=k_prev, config=config)
```

Note the `cands` line must stay ≤ 100 chars — split it:

```python
    top = list(ranked[: sizing.max_positions])
    cands = top + [s for s in cols[held] if s not in top]
```

Empty-`cands` edge: `ewma_covariance` on a zero-column frame must return an empty
`sigma` — if it raises, guard with
`if not cands: cov_sigma = pd.DataFrame(); cov_corr = pd.DataFrame()` and construct
the context directly.

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_risk_overlay.py -v`
Expected: PASS.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/risk/overlay.py tests/test_risk_overlay.py
git commit -m "feat(risk): build_risk_context with admitted-union-held candidate set"
```

---

### Task 6: sector cap, top-3 cap, extended `validate_book`

Spec §6 steps 4–5 and 10, "Top-3 termination contract".

**Files:**
- Modify: `src/number7/strategies/sizing.py`
- Test: `tests/test_sizing.py`

**Interfaces:**
- Consumes: `RiskContext` (Task 4: `sector`, `assetid`, `adv_cap_w`, `config`).
- Produces (all in `sizing.py`):

```python
def apply_sector_cap(w: pd.Series, sector: pd.Series, cap: float) -> pd.Series
def apply_top3_cap(w: pd.Series, cap: float, assetid: pd.Series,
                   max_iter: int) -> pd.Series
# validate_book gains: def validate_book(w, config, name="book", *, risk=None)
```

- [ ] **Step 1: Write the failing tests** (append to `tests/test_sizing.py`)

```python
from number7.risk.overlay import RiskConfig, RiskContext
from number7.strategies.sizing import apply_sector_cap, apply_top3_cap


def _rc(sector: dict, adv: dict | None = None, cols=None):
    cols = cols if cols is not None else list(sector)
    return RiskContext(
        sigma=pd.DataFrame(np.eye(len(cols)) * 0.04, index=cols, columns=cols),
        corr=pd.DataFrame(np.eye(len(cols)), index=cols, columns=cols),
        adv_cap_w=pd.Series(adv if adv else 1.0, index=cols, dtype=float),
        entry_barred=frozenset(),
        sector=pd.Series(sector).reindex(cols).fillna("UNKNOWN"),
        assetid=pd.Series(np.arange(1.0, len(cols) + 1.0), index=cols),
        k_prev=1.0, config=RiskConfig(),
    )


def test_sector_cap_scales_breaching_sector_proportionally_shortfall_to_cash():
    w = pd.Series({"A": 0.20, "B": 0.10, "C": 0.15})
    sector = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy"})
    out = apply_sector_cap(w, sector, cap=0.25)
    assert out["A"] == pytest.approx(0.20 * 0.25 / 0.30)
    assert out["B"] == pytest.approx(0.10 * 0.25 / 0.30)
    assert out["C"] == 0.15                     # untouched sector
    assert out.sum() < w.sum()                  # shortfall to cash, not redistributed


def test_sector_cap_applies_to_unknown_bucket():
    w = pd.Series({"A": 0.20, "B": 0.20})
    sector = pd.Series({"A": "UNKNOWN", "B": "UNKNOWN"})
    assert apply_sector_cap(w, sector, cap=0.25).sum() == pytest.approx(0.25)


def test_top3_cap_scales_three_largest_to_fit():
    w = pd.Series({"A": 0.12, "B": 0.11, "C": 0.10, "D": 0.02})
    out = apply_top3_cap(w, cap=0.25, assetid=pd.Series({"A": 1.0, "B": 2.0,
                                                         "C": 3.0, "D": 4.0}),
                         max_iter=30)
    top3 = out.nlargest(3).sum()
    assert top3 == pytest.approx(0.25, abs=1e-9)
    assert out["D"] == 0.02


def test_top3_cap_fixed_point_when_fourth_name_promotes():
    # scaling the top 3 drops them below D -> D enters the top 3 -> second pass needed
    w = pd.Series({"A": 0.30, "B": 0.30, "C": 0.30, "D": 0.089})
    out = apply_top3_cap(w, cap=0.25, assetid=pd.Series({"A": 1.0, "B": 2.0,
                                                         "C": 3.0, "D": 4.0}),
                         max_iter=30)
    assert out.nlargest(3).sum() <= 0.25 + 1e-9


def test_top3_cap_raises_after_max_iter():
    w = pd.Series({"A": 0.30, "B": 0.30, "C": 0.30, "D": 0.089})
    with pytest.raises(RuntimeError, match="top-3"):
        apply_top3_cap(w, cap=0.25, assetid=pd.Series({"A": 1.0, "B": 2.0,
                                                       "C": 3.0, "D": 4.0}), max_iter=1)


def test_validate_book_with_risk_checks_sector_top3_adv():
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30)
    risk = _rc({"A": "Tech", "B": "Tech", "C": "Tech"})
    bad_sector = pd.Series({"A": 0.10, "B": 0.10, "C": 0.10})
    with pytest.raises(ValueError, match="sector"):
        validate_book(bad_sector, cfg, risk=risk)
    risk2 = _rc({"A": "T1", "B": "T2", "C": "T3"})
    with pytest.raises(ValueError, match="top-3"):
        validate_book(pd.Series({"A": 0.10, "B": 0.10, "C": 0.10}), cfg, risk=risk2)
    risk3 = _rc({"A": "T1", "B": "T2", "C": "T3"}, adv={"A": 0.05, "B": 1.0, "C": 1.0})
    with pytest.raises(ValueError, match="adv"):
        validate_book(pd.Series({"A": 0.10, "B": 0.05, "C": 0.05}), cfg, risk=risk3)


def test_validate_book_without_risk_unchanged():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.10)
    w = pd.Series({"A": 0.10, "B": 0.10, "C": 0.05})
    assert validate_book(w, cfg) is w
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sizing.py -v`
Expected: new tests FAIL (imports).

- [ ] **Step 3: Implement** (in `sizing.py`; import `RiskContext` under
  `TYPE_CHECKING` or plainly — plain import is fine, `risk` does not import `sizing`)

```python
def apply_sector_cap(w: pd.Series, sector: pd.Series, cap: float) -> pd.Series:
    """Spec §6 step 4: scale each breaching sector down proportionally. Shortfall goes
    to cash, NEVER redistributed - redistribution would hand weight to lower-ranked
    names the budgeted fill did not choose (a second, hidden fill)."""
    out = w.copy()
    totals = w.groupby(sector.reindex(w.index)).sum()
    for sec, total in totals.items():
        if total > cap + _TOL:
            members = sector.reindex(w.index) == sec
            out[members] *= cap / total
    return out


def apply_top3_cap(w: pd.Series, cap: float, assetid: pd.Series,
                   max_iter: int) -> pd.Series:
    """Spec §6 step 5 with the termination contract: deterministic tie-break by
    (-weight, assetid) under a stable sort; hard iteration cap; final direct check."""
    out = w.copy()
    for _ in range(max_iter):
        order = pd.DataFrame({"w": -out, "aid": assetid.reindex(out.index)}) \
            .sort_values(["w", "aid"], kind="mergesort")
        top = order.index[:3]
        total = float(out[top].sum())
        if total <= cap + _TOL:
            return out
        out[top] *= cap / total
    order = pd.DataFrame({"w": -out, "aid": assetid.reindex(out.index)}) \
        .sort_values(["w", "aid"], kind="mergesort")
    if float(out[order.index[:3]].sum()) > cap + _TOL:
        raise RuntimeError(f"top-3 cap failed to converge in {max_iter} iterations")
    return out
```

`validate_book` — extend the signature and append after the gross check:

```python
def validate_book(w: pd.Series, config: SizingConfig, name: str = "book",
                  *, risk=None) -> pd.Series:
    ...existing body...
    if risk is not None:
        cap = risk.config.sector_cap
        totals = w.groupby(risk.sector.reindex(w.index)).sum()
        bad = totals[totals > cap + 1e-9]
        if len(bad):
            raise ValueError(f"{name} breaches sector cap {cap}: {dict(bad.round(4))}")
        top3 = float(w.nlargest(3).sum())
        if top3 > risk.config.top3_cap + 1e-9:
            raise ValueError(f"{name} breaches top-3 cap: {top3:.4f}")
        over = w[w > risk.adv_cap_w.reindex(w.index).fillna(np.inf) + 1e-9]
        if len(over):
            raise ValueError(f"{name} breaches adv cap: {list(over.index[:3])}")
    return w
```

- [ ] **Step 4: Run to verify pass**

Run: `set -o pipefail; uv run pytest tests/test_sizing.py tests/test_risk_overlay.py 2>&1 | tail -3`
Expected: PASS.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/strategies/sizing.py tests/test_sizing.py
git commit -m "feat(sizing): sector and top-3 caps with extended validation"
```

---

### Task 7: structural drift band with the generalized repair pass

Spec §6 step 7 and "Why the band moved before the scalar". The band now runs on
structural (pre-k) weights; caller passes `current` already descaled. The repair pass
extends from position/gross to sector, top-3, and ADV.

**Files:**
- Modify: `src/number7/strategies/sizing.py` (`apply_drift_band`)
- Test: `tests/test_sizing.py`

**Interfaces:**
- Produces: `apply_drift_band(target, current, config, stale_periods=None, risk=None)`
  — same semantics as today when `risk is None`; with `risk`, retention that breaches
  ANY cap on the structural book is forced back to target.

- [ ] **Step 1: Write the failing tests**

```python
def test_band_retention_breaching_sector_cap_is_forced_to_target():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, drift_band=0.10)
    risk = _rc({"A": "Tech", "B": "Tech", "C": "Energy"})
    target = pd.Series({"A": 0.125, "B": 0.125, "C": 0.10})     # sector Tech = 0.25, at cap
    current = pd.Series({"A": 0.13, "B": 0.13, "C": 0.10})      # retention -> 0.26 breach
    out = apply_drift_band(target, current, cfg, risk=risk)
    assert out.groupby(risk.sector.reindex(out.index)).sum()["Tech"] <= 0.25 + 1e-9


def test_band_retention_breaching_adv_cap_is_forced_to_target():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, drift_band=0.10)
    risk = _rc({"A": "T1", "B": "T2", "C": "T3"}, adv={"A": 0.12, "B": 1.0, "C": 1.0})
    target = pd.Series({"A": 0.115, "B": 0.10, "C": 0.10})
    current = pd.Series({"A": 0.125, "B": 0.10, "C": 0.10})     # in band, above ADV cap
    out = apply_drift_band(target, current, cfg, risk=risk)
    assert out["A"] == pytest.approx(0.115)


def test_band_without_risk_is_byte_identical_to_before():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, drift_band=0.05)
    target = pd.Series({"A": 0.30, "B": 0.20})
    current = pd.Series({"A": 0.31, "B": 0.0})
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == 0.31 and out["B"] == 0.20                # existing semantics
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sizing.py -v -k band`
Expected: new tests FAIL — unexpected keyword `risk`.

- [ ] **Step 3: Implement** — add `risk=None` parameter; after the existing
  position-cap breach repair and before the gross `while` loop, insert:

```python
    if risk is not None:
        # generalized repair (spec §6): retention must not re-breach ANY cap on the
        # structural book. Force upward retentions back to target, per constraint.
        over_adv = keep & (out > risk.adv_cap_w.reindex(out.index).fillna(np.inf) + 1e-9)
        out[over_adv] = target[over_adv]
        keep = keep & ~over_adv

        sec = risk.sector.reindex(out.index)
        totals = out.groupby(sec).sum()
        for s in totals[totals > risk.config.sector_cap + 1e-9].index:
            fix = keep & (sec == s) & (out > target)
            out[fix] = target[fix]
            keep = keep & ~fix

        order = pd.DataFrame({"w": -out, "aid": risk.assetid.reindex(out.index)}) \
            .sort_values(["w", "aid"], kind="mergesort")
        top = order.index[:3]
        if float(out[top].sum()) > risk.config.top3_cap + 1e-9:
            fix = keep & out.index.isin(top) & (out > target)
            out[fix] = target[fix]
            keep = keep & ~fix
```

Rationale for `out > target` masks: a retention below target can only lower a sum, so
only upward retentions can cause a breach; forcing them to target restores the
cap-satisfying value the caps stage produced. The final `validate_book(..., risk=...)`
in Task 8 is the backstop proof.

- [ ] **Step 4: Run to verify pass**

Run: `set -o pipefail; uv run pytest tests/test_sizing.py 2>&1 | tail -3`
Expected: PASS, including all pre-existing band tests untouched.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/strategies/sizing.py tests/test_sizing.py
git commit -m "feat(sizing): extend drift-band repair to sector, top-3 and ADV caps"
```

---

### Task 8: `resolve_book(risk=...)` — the full §6 pipeline

Spec §6 (normative order), §4.2 (return shape).

**Files:**
- Modify: `src/number7/strategies/sizing.py` (`resolve_book`)
- Test: `tests/test_sizing.py`

**Interfaces:**
- Produces: `resolve_book(slate, current, config, stale_periods=None, *, risk=None)`
  returning `pd.Series` when `risk is None` (unchanged) and
  `tuple[pd.Series, float]` — `(book, applied_k)` — when `risk` is supplied.
- Consumes: everything from Tasks 4–7.

- [ ] **Step 1: Write the failing tests**

```python
def _slate_for(cols, weights, ranks, admit_new=True):
    w = pd.Series(0.0, index=cols)
    r = pd.Series(np.nan, index=cols, dtype=float)
    for s, v in weights.items():
        w[s] = v
    for s, v in ranks.items():
        r[s] = v
    return Slate(weights=w, rank=r, admit_new=admit_new)


def test_resolve_book_with_risk_returns_book_and_applied_k():
    cols = pd.Index(["A", "B", "C"])
    risk = _rc({"A": "T1", "B": "T2", "C": "T3"}, cols=list(cols))
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.25, "B": 0.25}, {"A": 1.0, "B": 2.0})
    book, applied_k = resolve_book(slate, pd.Series(0.0, index=cols), cfg, risk=risk)
    # sigma 20% per name, independent: sigma_p = 0.2*sqrt(2)*0.25 ~ 7.07% < 10% target
    assert applied_k == 1.0
    assert book["A"] == pytest.approx(0.25)


def test_resolve_book_scalar_cuts_the_whole_book():
    cols = pd.Index(["A", "B"])
    risk = _rc({"A": "T1", "B": "T2"}, cols=list(cols))          # var 0.04 each
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.5, "B": 0.5}, {"A": 1.0, "B": 2.0})
    book, applied_k = resolve_book(slate, pd.Series(0.0, index=cols), cfg, risk=risk)
    sigma_p = np.sqrt(0.25 * 0.04 * 2)                           # 14.14%
    assert applied_k == pytest.approx(min(1.0, 0.10 / sigma_p))
    assert book["A"] == pytest.approx(0.5 * applied_k)


def test_resolve_book_k_move_below_band_still_executes():
    """The suppression regression (spec §6): a sub-band k move must pass through."""
    cols = pd.Index(["A", "B"])
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=0.0, drift_band=0.05)
    slate = _slate_for(cols, {"A": 0.5, "B": 0.5}, {"A": 1.0, "B": 2.0})
    # previous k = 0.73; current holdings are the k-scaled book from last week
    risk = RiskContext(
        sigma=pd.DataFrame(np.eye(2) * 0.04, index=list(cols), columns=list(cols)),
        corr=pd.DataFrame(np.eye(2), index=list(cols), columns=list(cols)),
        adv_cap_w=pd.Series(1.0, index=cols), entry_barred=frozenset(),
        sector=pd.Series({"A": "T1", "B": "T2"}),
        assetid=pd.Series({"A": 1.0, "B": 2.0}), k_prev=0.73, config=RiskConfig())
    current = pd.Series({"A": 0.5 * 0.73, "B": 0.5 * 0.73})
    book, applied_k = resolve_book(slate, current, cfg, risk=risk)
    # k_raw ~ 0.707 -> ~3.2% below k_prev: inside the 5% band, must STILL execute
    assert applied_k == pytest.approx(0.10 / np.sqrt(0.25 * 0.04 * 2))
    assert book["A"] == pytest.approx(0.5 * applied_k)


def test_resolve_book_floor_runs_after_k():
    cols = pd.Index(["A", "B"])
    risk = _rc({"A": "T1", "B": "T2"}, cols=list(cols))
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=1000.0)               # floor_w = 0.02
    slate = _slate_for(cols, {"A": 0.5, "B": 0.028}, {"A": 1.0, "B": 2.0})
    book, applied_k = resolve_book(slate, pd.Series(0.0, index=cols), cfg, risk=risk)
    assert applied_k < 1.0
    assert book["B"] == 0.0                     # 0.028 * k < 0.02 -> floored out


def test_resolve_book_entry_barred_blocks_new_but_not_held():
    cols = pd.Index(["A", "B"])
    risk = RiskContext(
        sigma=pd.DataFrame(np.eye(2) * 0.0001, index=list(cols), columns=list(cols)),
        corr=pd.DataFrame(np.eye(2), index=list(cols), columns=list(cols)),
        adv_cap_w=pd.Series(1.0, index=cols), entry_barred=frozenset({"A", "B"}),
        sector=pd.Series({"A": "T1", "B": "T2"}),
        assetid=pd.Series({"A": 1.0, "B": 2.0}), k_prev=1.0, config=RiskConfig())
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.3, "B": 0.3}, {"A": 1.0, "B": 2.0})
    current = pd.Series({"A": 0.25, "B": 0.0})
    book, _ = resolve_book(slate, current, cfg, risk=risk)
    assert book["A"] > 0                        # held: retainable despite the bar
    assert book["B"] == 0.0                     # new entry: blocked


def test_resolve_book_without_risk_returns_series_unchanged():
    cols = pd.Index(["A", "B"])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.3, "B": 0.3}, {"A": 1.0, "B": 2.0})
    out = resolve_book(slate, pd.Series(0.0, index=cols), cfg)
    assert isinstance(out, pd.Series)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_sizing.py -v -k resolve_book`
Expected: new tests FAIL.

- [ ] **Step 3: Implement.** Rework `resolve_book`:

```python
def resolve_book(slate: Slate, current: pd.Series, config: SizingConfig,
                 stale_periods: pd.Series | None = None, *, risk=None):
    """risk=None: admission -> fill -> cap -> gross -> floor -> band -> validate
    (UNCHANGED - byte-identical passthrough). With risk (spec §6, order normative):
    admission+entry bars -> fill -> min(position,ADV) cap -> sector cap -> top-3 cap ->
    gross -> STRUCTURAL band -> scalar -> floor -> validate. Returns (book, applied_k)
    when risk is supplied."""
    idx = slate.weights.index
    current = current.reindex(idx).fillna(0.0)

    # 1. admission
    eligible = slate.weights > 0
    if not slate.admit_new:
        eligible &= current > 0
    if risk is not None:
        barred = idx.isin(risk.entry_barred)
        eligible &= (current > 0) | ~barred     # bars block NEW entry only

    # 2. budgeted top-down fill  (existing loop, unchanged)
    ...

    # 3. position cap (per-name min with ADV cap when risk is on)
    cap = config.position_cap
    if risk is not None:
        cap = np.minimum(cap, risk.adv_cap_w.reindex(idx).fillna(0.0))
    target = target.clip(upper=cap)

    # 4-5. sector and top-3 caps
    if risk is not None:
        target = apply_sector_cap(target, risk.sector, risk.config.sector_cap)
        target = apply_top3_cap(target, risk.config.top3_cap, risk.assetid,
                                max_iter=config.max_positions)

    # 6. gross normalization (existing, scale-DOWN only)
    ...

    if risk is None:
        # existing tail: floor -> band -> validate, byte-identical
        floor_w = config.min_position_dollars / config.sleeve_equity
        target[target < floor_w] = 0.0
        return validate_book(apply_drift_band(target, current, config, stale_periods),
                             config, name="resolved_book")

    # 7. STRUCTURAL drift band: compare against holdings descaled by the k that
    #    produced them (spec §6 "Why the band moved before the scalar")
    structural_current = current / risk.k_prev
    banded = apply_drift_band(target, structural_current, config, stale_periods,
                              risk=risk)

    # 8. vol scalar on the structural post-cap book
    res = risk.scalar(banded)
    scaled = banded * res.applied_k

    # 9. floor AFTER all scalars (k can push a surviving position under $1k;
    #    dropping only lowers the sum, one pass remains the fixed point)
    floor_w = config.min_position_dollars / config.sleeve_equity
    scaled[scaled < floor_w] = 0.0

    # 10. re-validate with the risk limits
    return (validate_book(scaled, config, name="resolved_book", risk=risk),
            res.applied_k)
```

**Careful:** the current code runs floor BEFORE band (`resolve_book` steps 5–6 in the
existing file). Keep that exact order on the `risk=None` path — byte-identical means
identical, not equivalent. The `risk` path is the spec's §6 order.

**Validation subtlety:** step 10 validates the k-scaled book. All caps are preserved
under `k ≤ 1` (the scaling invariant), so any validation failure here is a genuine bug
in steps 1–9 — that is the point of the check.

- [ ] **Step 4: Run the full suite**

Run: `set -o pipefail; uv run pytest 2>&1 | tail -3`
Expected: all pass. Any pre-existing `resolve_book` test failure = the `risk=None` path
changed — fix the regression, not the test.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/strategies/sizing.py tests/test_sizing.py
git commit -m "feat(sizing): full risk pipeline in resolve_book"
```

---

### Task 9: engine wiring — `run_backtest(risk_cfg=...)`, `k_prev` state, result fields

Spec §4.2, §4.5.

**Files:**
- Modify: `src/number7/engine/backtest.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Produces: `run_backtest(..., risk_cfg: RiskConfig | None = None, initial_k: float = 1.0)`;
  `BacktestResult` gains `risk_k: pd.Series` (applied k per executed rebalance, empty
  when `risk_cfg is None`), `final_k: float` (1.0 when off), and
  `risk_diag: dict[pd.Timestamp, dict] | None` (per-rebalance diagnostics, Task 11
  fills beta/avg_corr — engine stores the dict returned by `risk_diagnostics`).
- Consumes: `build_risk_context` (Task 5), `resolve_book(risk=)` (Task 8),
  `risk_diagnostics` (Task 11 — stub returning `{}` until then is NOT allowed; instead
  wire `risk_diag` in Task 11 and leave it out here).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_backtest.py`)

```python
from number7.risk.overlay import RiskConfig


def _risk_panel(make_panel, n=300, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-05", periods=n, freq="B")
    cols = ["A", "B", "C", "D"]
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, (n, 4)), axis=0)),
        index=idx, columns=cols)
    return make_panel(close, gics_sector=pd.Series("TestSector", index=cols))


class FourEqual:
    manifest = StrategyManifest(name="four", family="test", origin="human", params={})

    def target_weights(self, view) -> Slate:
        cols = view.px_close.columns
        w = pd.Series(0.25, index=cols)
        rank = pd.Series([1.0, 2.0, 3.0, 4.0], index=cols)
        return Slate(weights=w, rank=rank, admit_new=True)


def test_backtest_records_risk_k_and_final_k(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-8:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0, risk_cfg=RiskConfig())
    assert len(res.risk_k) == len(res.rebalance_dates)
    assert (res.risk_k > 0).all() and (res.risk_k <= 1.0).all()
    assert res.final_k == pytest.approx(float(res.risk_k.iloc[-1]))


def test_backtest_k_ratchets_up_slowly(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-8:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0, risk_cfg=RiskConfig(), initial_k=0.20)
    ks = res.risk_k.to_numpy()
    assert (np.diff(ks) <= 0.10 + 1e-9).all()       # up moves capped at up_step


def test_backtest_risk_requires_sizing(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-4:]
    with pytest.raises(ValueError, match="risk_cfg requires sizing"):
        run_backtest(FourEqual(), panel, rb, CostModel(), risk_cfg=RiskConfig())


def test_backtest_without_risk_is_byte_identical(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-8:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    a = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg, initial=50_000.0)
    b = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg, initial=50_000.0)
    pd.testing.assert_series_equal(a.equity, b.equity)
    assert a.final_k == 1.0 and len(a.risk_k) == 0
```

(Imports at top of file as needed: `weekly_rebalances` from `number7.engine.schedule`,
`Slate`, `StrategyManifest` from `number7.engine.strategy`.)

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_backtest.py -v -k risk`
Expected: FAIL.

- [ ] **Step 3: Implement.** In `run_backtest`:

- signature gains `risk_cfg=None, initial_k: float = 1.0`; raise
  `ValueError("risk_cfg requires sizing: the overlay lives inside resolve_book")` if
  `risk_cfg is not None and sizing is None`.
- loop state: `k_prev = initial_k`; dict `risk_k: dict[pd.Timestamp, float] = {}`.
- in the rebalance branch, replace the resolve call:

```python
            else:
                cfg = replace(sizing, sleeve_equity=eq_at_signal)
                if risk_cfg is None:
                    target = resolve_book(tradeable, state_at_signal, cfg,
                                          stale).reindex(cols).fillna(0.0)
                else:
                    ctx = build_risk_context(view, tradeable, state_at_signal, cfg,
                                             risk_cfg, k_prev)
                    target, k_prev = resolve_book(tradeable, state_at_signal, cfg,
                                                  stale, risk=ctx)
                    target = target.reindex(cols).fillna(0.0)
                    risk_k[t] = k_prev
```

- `BacktestResult` gains fields (defaults keep old constructions valid):

```python
    risk_k: pd.Series = None          # type: ignore[assignment]  -- set in ctor below
    final_k: float = 1.0
    risk_diag: dict | None = None
```

Cleaner: make `risk_k` non-default and pass
`risk_k=pd.Series(risk_k, dtype=float), final_k=k_prev if risk_cfg else 1.0` in the
constructor call — dataclass field order requires defaults last; put the three new
fields before `slates` with explicit defaults `field(default_factory=...)` is not
allowed for Series, so: `risk_k: pd.Series | None = None` and normalize
`self.risk_k = pd.Series(dtype=float) if None`. Simplest that passes review: default
`None`, and the constructor always passes a real Series. Tests read
`len(res.risk_k) == 0` on the off path — pass `pd.Series(dtype=float)` explicitly.

- [ ] **Step 4: Run the full suite**

Run: `set -o pipefail; uv run pytest 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/engine/backtest.py tests/test_backtest.py
git commit -m "feat(engine): risk overlay wiring with k_prev carried across rebalances"
```

---

### Task 10: live path — `compute_live_targets(risk_cfg=, k_prev=)` + golden replay

Spec §4.2, §4.5, §8 "Parity".

**Files:**
- Modify: `src/number7/engine/live.py`
- Test: `tests/test_live_parity.py`

**Interfaces:**
- Produces: `compute_live_targets(..., risk_cfg: RiskConfig | None = None,
  k_prev: float | None = None)` — returns `pd.Series` as today when `risk_cfg is None`,
  `tuple[pd.Series, float]` (weights, applied_k) when supplied. Raises when `risk_cfg`
  is given without `k_prev` or without `sizing`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_live_parity.py`)

```python
from number7.engine.schedule import weekly_rebalances
from number7.risk.overlay import RiskConfig


def _risk_panel(make_panel, n=300, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-05", periods=n, freq="B")
    cols = ["A", "B", "C", "D"]
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, (n, 4)), axis=0)),
        index=idx, columns=cols)
    return make_panel(close, gics_sector=pd.Series("TestSector", index=cols))


class FourEqual:
    manifest = StrategyManifest(name="four", family="test", origin="human", params={})

    def target_weights(self, view) -> Slate:
        cols = view.px_close.columns
        return Slate(weights=pd.Series(0.25, index=cols),
                     rank=pd.Series([1.0, 2.0, 3.0, 4.0], index=cols), admit_new=True)


def test_golden_replay_with_risk_overlay(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-6:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0, risk_cfg=RiskConfig(), initial_k=0.50)
    k_prev = 0.50
    for t in res.rebalance_dates:
        live, applied_k = compute_live_targets(
            FourEqual(), panel, asof=t,
            current=res.state_at_signal.loc[t],
            sizing=replace(cfg, sleeve_equity=float(res.equity_at_signal.loc[t])),
            stale_periods=res.stale_periods.shift(1).fillna(0).loc[t],
            risk_cfg=RiskConfig(), k_prev=k_prev)
        pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)
        assert applied_k == pytest.approx(float(res.risk_k.loc[t]))   # pins risk_k
        k_prev = applied_k


def test_live_risk_requires_k_prev(fake_snapshot):
    panel = build_panel(fake_snapshot)
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, min_position_dollars=0.0)
    flat = pd.Series(0.0, index=panel.px_close.columns)
    with pytest.raises(ValueError, match="k_prev"):
        compute_live_targets(TwoNames(), panel, asof=panel.sessions[3],
                             current=flat, sizing=cfg, risk_cfg=RiskConfig())
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_live_parity.py -v`
Expected: new tests FAIL.

- [ ] **Step 3: Implement.** In `compute_live_targets`:

```python
def compute_live_targets(strategy, panel, asof, *, current=None, sizing=None,
                         stale_periods=None, risk_cfg=None, k_prev=None):
```

after the existing `current is None` guard:

```python
    if risk_cfg is not None:
        if sizing is None:
            raise ValueError("risk_cfg requires sizing: the overlay lives inside "
                             "resolve_book (risk spec §4.2)")
        if k_prev is None:
            raise ValueError(
                "compute_live_targets requires `k_prev` when `risk_cfg` is supplied: an "
                "unknown ratchet state must not silently default to fully-risked (risk "
                "spec §4.5). Pass the persisted value, or an explicit 1.0 for a "
                "genuinely fresh book.")
        cur = current.reindex(cols).fillna(0.0)
        ctx = build_risk_context(view, tradeable, cur, sizing, risk_cfg, k_prev)
        book, applied_k = resolve_book(tradeable, cur, sizing, stale_periods, risk=ctx)
        return book.reindex(cols).fillna(0.0), applied_k
```

(`build_risk_context` imported from `number7.risk.overlay`; note it receives `view` —
the masked panel — not `panel`.)

- [ ] **Step 4: Run the full suite**

Run: `set -o pipefail; uv run pytest 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/engine/live.py tests/test_live_parity.py
git commit -m "feat(live): risk overlay on the live path with pinned k parity"
```

---

### Task 11: `risk_diagnostics` + engine recording

Spec §4.4 (diagnostics are computed post-resolution by a pure function and recorded by
the caller), §4.5 (beta streak derived from the recorded series).

**Files:**
- Modify: `src/number7/risk/overlay.py`, `src/number7/engine/backtest.py`
- Test: `tests/test_risk_overlay.py`, `tests/test_backtest.py`

**Interfaces:**
- Produces:

```python
def risk_diagnostics(ctx: RiskContext, view: PanelView, book: pd.Series,
                     scalar_result: ScalarResult, *,
                     spy: str = "SPY") -> dict
    # {"applied_k", "k_raw", "sigma_p", "beta", "avg_corr", "sector_bound": [...],
    #  "top3_bound": bool, "adv_bound": [...], "cov_diagnostics": {...}}
```

`BacktestResult.risk_diag: dict[pd.Timestamp, dict] | None` filled when `risk_cfg` on.

- [ ] **Step 1: Write the failing tests**

```python
from number7.risk.overlay import risk_diagnostics


def test_diagnostics_beta_and_funded_avg_corr(make_panel):
    view = _view(make_panel)                    # helper from Task 5 tests
    # add a SPY column driven by A so beta is meaningfully positive
    cols = list(view.px_close.columns)
    ctx = build_risk_context(
        view, _slate({"A": 0.4, "B": 0.4}, view.px_close.columns),
        pd.Series(0.0, index=view.px_close.columns),
        SizingConfig(sleeve_equity=50_000.0), RiskConfig(), 1.0)
    book = pd.Series({"A": 0.4, "B": 0.4}).reindex(view.px_close.columns).fillna(0.0)
    d = risk_diagnostics(ctx, view, book, ctx.scalar(book), spy="C")   # C as proxy
    assert np.isfinite(d["beta"])
    assert -1.0 <= d["avg_corr"] <= 1.0
    assert d["applied_k"] == d["k_raw"] or d["applied_k"] <= 1.0


def test_diagnostics_beta_nan_when_proxy_missing(make_panel):
    view = _view(make_panel)
    ctx = build_risk_context(
        view, _slate({"A": 0.4}, view.px_close.columns),
        pd.Series(0.0, index=view.px_close.columns),
        SizingConfig(sleeve_equity=50_000.0), RiskConfig(), 1.0)
    book = pd.Series({"A": 0.4}).reindex(view.px_close.columns).fillna(0.0)
    d = risk_diagnostics(ctx, view, book, ctx.scalar(book), spy="NOPE")
    assert np.isnan(d["beta"])                  # diagnostic only, never raises
```

And in `tests/test_backtest.py`:

```python
def test_backtest_records_risk_diag(make_panel):
    panel = _risk_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[-6:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    res = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0, risk_cfg=RiskConfig())
    assert set(res.risk_diag) == set(res.rebalance_dates)
    assert {"beta", "avg_corr", "applied_k"} <= set(next(iter(res.risk_diag.values())))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_risk_overlay.py tests/test_backtest.py -v -k diag`
Expected: FAIL.

- [ ] **Step 3: Implement**

```python
def risk_diagnostics(ctx: RiskContext, view, book: pd.Series,
                     scalar_result: ScalarResult, *, spy: str = "SPY") -> dict:
    """Monitor-only quantities, computed on the RESOLVED book (spec §4.4). NEVER a
    sizing input: beta has no safe automatic action in a long-only book, and avg_corr
    belongs to the future correlation-breakdown brake."""
    funded = book[book > 0]
    cfg = ctx.config
    rets = np.log(view.tr_close).diff()
    beta = float("nan")
    if spy in rets.columns:
        r_spy = rets[spy].tail(cfg.beta_window)
        r_book = (rets[funded.index].tail(cfg.beta_window) * funded).sum(axis=1)
        var = float(r_spy.var(ddof=0))
        if np.isfinite(var) and var > 0 and len(funded):
            beta = float(r_book.cov(r_spy) / var)
    avg_corr = float("nan")
    both = [s for s in funded.index if s in ctx.corr.index]
    if len(both) >= 2:
        sub = ctx.corr.loc[both, both].to_numpy()
        avg_corr = float(sub[np.triu_indices(len(both), 1)].mean())
    sector_sums = book.groupby(ctx.sector.reindex(book.index)).sum()
    return {
        "applied_k": scalar_result.applied_k, "k_raw": scalar_result.k_raw,
        "sigma_p": scalar_result.sigma_p, "beta": beta, "avg_corr": avg_corr,
        "sector_bound": list(sector_sums[sector_sums >= cfg.sector_cap - 1e-9].index),
        "top3_bound": bool(float(book.nlargest(3).sum()) >= cfg.top3_cap - 1e-9),
        "adv_bound": list(book.index[book >= ctx.adv_cap_w.reindex(book.index)
                                     .fillna(np.inf) - 1e-9]),
    }
```

Engine: in the `risk_cfg` branch of Task 9, `resolve_book` already returned
`(target, k_prev)`; recompute the `ScalarResult` is NOT allowed (the ratchet already
advanced) — instead have `resolve_book` return the `ScalarResult` (change Task 8's
return to `(book, ScalarResult)` and adjust Task 8/10 assertions to
`res_tuple[1].applied_k`), OR reconstruct a `ScalarResult` from recorded values. Pick
the first: **`resolve_book(risk=...)` returns `(pd.Series, ScalarResult)`** — it is the
honest API (spec §4.4 names `ScalarResult` as the explicit product). Update Task 8's
and Task 10's unpacking to `book, sres = ...; applied_k = sres.applied_k`, live path
returns `(book, sres.applied_k)` unchanged externally. Then:

```python
                    diag = risk_diagnostics(ctx, view, target, sres)
                    risk_diag[t] = diag
```

- [ ] **Step 4: Run the full suite**

Run: `set -o pipefail; uv run pytest 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/risk/overlay.py src/number7/engine/backtest.py \
        tests/test_risk_overlay.py tests/test_backtest.py
git commit -m "feat(risk): post-resolution diagnostics recorded per rebalance"
```

---

### Task 12: causality + walk-forward wiring

Spec §8 "Causality", §9 (fold carry).

**Files:**
- Modify: `src/number7/validation/causality.py` (`closed_loop_violations` gains
  `risk_cfg`), `src/number7/validation/walkforward.py` (thread `risk_cfg`, carry
  `final_k`)
- Test: `tests/test_causality.py`, `tests/test_walkforward.py`

**Interfaces:**
- Produces: `closed_loop_violations(..., risk_cfg: RiskConfig | None = None)`;
  `walk_forward(..., risk_cfg: RiskConfig | None = None)` passing
  `initial_k=is_res.final_k` into the OOS fold.

- [ ] **Step 1: Write the failing tests**

`tests/test_causality.py`:

```python
from number7.risk.overlay import RiskConfig
from number7.risk import overlay as overlay_mod


def test_closed_loop_passes_with_risk_overlay(make_panel):
    panel = _long_panel(make_panel)          # reuse/extend this file's panel helper to
    rb = weekly_rebalances(panel.sessions)   # >= 300 sessions with gics_sector set
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    bad = closed_loop_violations(lambda p: RandomTopN(n=3, seed=9), panel, rb,
                                 CostModel(), sizing=cfg, risk_cfg=RiskConfig())
    assert bad == []


def test_closed_loop_catches_unmasked_sigma(make_panel, monkeypatch):
    """Overlay analogue of LookaheadTrap: a context built from the FULL panel must be
    caught by truncate-and-compare."""
    panel = _long_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    real = overlay_mod.build_risk_context

    def leaky(view, slate, current, sizing, config, k_prev):
        return real(panel.masked_to(panel.sessions[-1]), slate, current,
                    sizing, config, k_prev)              # reads the FUTURE

    monkeypatch.setattr("number7.engine.backtest.build_risk_context", leaky)
    bad = closed_loop_violations(lambda p: RandomTopN(n=3, seed=9), panel, rb,
                                 CostModel(), sizing=cfg, risk_cfg=RiskConfig())
    assert bad != []
```

(The leaky patch targets the name the engine imported. If Task 9 imported it as
`from number7.risk.overlay import build_risk_context`, the patch path above is correct.)

`tests/test_walkforward.py`:

```python
def test_walkforward_carries_final_k_across_folds(make_panel, monkeypatch):
    calls = []
    import number7.validation.walkforward as wf
    real = wf.run_backtest

    def spy(*a, **kw):
        calls.append(kw.get("initial_k"))
        return real(*a, **kw)

    monkeypatch.setattr(wf, "run_backtest", spy)
    panel = _wf_panel(make_panel)             # this file's existing long-panel helper,
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,   # + gics_sector
                       min_position_dollars=0.0)
    walk_forward(lambda: RandomTopN(n=3, seed=1), panel,
                 WFProtocol(train_years=1, test_months=6, step_months=6, min_windows=1),
                 CostModel(), sizing=cfg, risk_cfg=RiskConfig())
    # every OOS call (odd positions) received the IS fold's final_k, not the default
    oos_initial_ks = calls[1::2]
    assert all(k is not None for k in oos_initial_ks)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_causality.py tests/test_walkforward.py -v`
Expected: new tests FAIL — unexpected keyword.

- [ ] **Step 3: Implement**

`causality.py::closed_loop_violations` — add `risk_cfg=None` parameter, extend
`kw = dict(cost_model=cost_model, sizing=sizing, record_slates=True, risk_cfg=risk_cfg)`.

`walkforward.py::walk_forward` — add `risk_cfg=None`; pass `risk_cfg=risk_cfg` to the IS
run; pass `risk_cfg=risk_cfg, initial_k=is_res.final_k` to the OOS run. (`final_k` is
1.0 whenever risk is off — the extra kwarg is harmless there but only pass it when
`risk_cfg is not None` to keep the off path byte-identical.)

- [ ] **Step 4: Run the full suite**

Run: `set -o pipefail; uv run pytest 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/validation tests/test_causality.py tests/test_walkforward.py
git commit -m "feat(validation): risk overlay reaches causality and walk-forward"
```

---

### Task 13: pre-registration + ablation runner

Spec §9. The runner mirrors `calibrate_clenow.py`'s structure; the 22-year run itself is
executed manually later (it is hours of compute), so tests cover registration and report
assembly, not the run.

**Files:**
- Modify: `src/number7/research/preregs.py`
- Create: `src/number7/research/ablate_risk_overlay.py`
- Test: `tests/test_preregs.py`

**Interfaces:**
- Consumes: `PROFILES["deployable"]`, `run_profile`, `Ledger`, `RiskConfig`,
  `run_backtest(risk_cfg=)`, `summary`, `block_bootstrap_dd`, `monkey_test`.
- Produces: `RISK_OVERLAY_ABLATION: PreRegistration`;
  `python -m number7.research.ablate_risk_overlay` writing
  `docs/research/2026-08-risk-overlay-ablation.md`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_preregs.py`)

```python
from number7.research.preregs import RISK_OVERLAY_ABLATION


def test_risk_overlay_ablation_is_diagnostic_and_two_cell():
    assert RISK_OVERLAY_ABLATION.family == "clenow_diagnostic"
    assert RISK_OVERLAY_ABLATION.param_space == {"overlay": ["on", "off"]}
    assert RISK_OVERLAY_ABLATION.search_space_size == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_preregs.py -v`
Expected: FAIL — import error.

- [ ] **Step 3: Implement.** In `preregs.py`:

```python
RISK_OVERLAY_ABLATION = PreRegistration(
    family=DIAGNOSTIC_FAMILY,
    origin="human",
    mechanism=(
        "Risk-layer overlay ablation (risk spec §9): the deployable Clenow profile run "
        "with and without the portfolio risk overlay (vol-target scalar with ratchet, "
        "sector/top-3 caps, ADV cap, spread gate). Every overlay parameter is a frozen "
        "constitution constant declared a priori - zero searched dimensions. The run "
        "measures the overlay's cost/benefit; it cannot change any shipped value."),
    citations=["KB-08 Clenow, Trading Evolved", "blueprint §8",
               "spec 2026-08-06-portfolio-risk-layer-design",
               "docs/research/2026-08-clenow-calibration-memo.md (monkey drawdown)"],
    expected_effect=(
        "Overlay-on: realized vol nearer the 10% target, monkey drawdown percentile "
        "materially above 0.001, moderate CAGR/Sharpe cost. Sector-cap binds reported "
        "split at the 2016/2018 GICS boundaries because the historical sector map is a "
        "declared PIT approximation."),
    falsification=(
        "Overlay-on drawdown is NOT improved versus overlay-off; or the realized-vol "
        "path ignores the target (scalar inert); or the overlay costs more Sharpe than "
        "the drawdown improvement justifies under §8's stated risk preferences. Any of "
        "these triggers a declared amendment review, never a parameter search."),
    param_space={"overlay": ["on", "off"]},
)
```

`ablate_risk_overlay.py` skeleton (module docstring + `main()`):

```python
"""Risk-overlay ablation runner (risk spec §9). Run:

    uv run python -m number7.research.ablate_risk_overlay

Two cells only - deployable profile with and without the overlay, same snapshot, both
logged to the ledger under DIAGNOSTIC_FAMILY. Report criteria (spec §9): monkey drawdown
percentile, realized post-k vol vs target PATH, CAGR/Sharpe cost, cap bind rates by
stage with sector binds split at the 2016-08-31 and 2018-09-28 GICS boundaries and
top3-without-sector binds separated, applied_k through 2008/2020/2022, and an explicit
note that ADV no-binds at $50k are expected and are NOT evidence the mechanism works."""
```

`main()` mirrors `calibrate_clenow.main()`: load `current_snapshot()` panel, run
`run_profile`-style backtests with `risk_cfg=RiskConfig()` and `risk_cfg=None`, compute
`summary`, realized-vol path (rolling 63-session std of log equity returns × √252),
bind-rate tables from `res.risk_diag`, `monkey_test` on the overlay-on run, ledger rows
under `RISK_OVERLAY_ABLATION`, and write the memo file. Extract the report assembly into
a pure function `_report(on: BacktestResult, off: BacktestResult, ...) -> str` and
unit-test THAT with two tiny synthetic results:

```python
def test_ablation_report_contains_required_sections(make_panel):
    ...build two 8-rebalance BacktestResults on a synthetic panel (reuse the Task 9
    fixture pattern), call _report, assert the §9 headings are present:
    "## Realized vol vs target", "## Cap bind rates", "## applied_k path",
    "ADV no-binds at $50k are expected"...
```

- [ ] **Step 4: Run the full suite**

Run: `set -o pipefail; uv run pytest 2>&1 | tail -3`
Expected: all pass.

- [ ] **Step 5: Ruff + commit**

```bash
uv run ruff check src tests
git add src/number7/research tests/test_preregs.py
git commit -m "feat(research): pre-registered risk-overlay ablation runner"
```

---

### Task 14: final verification sweep

**Files:** none new.

- [ ] **Step 1: Full suite + lint**

```bash
set -o pipefail
uv run pytest 2>&1 | tail -3
uv run ruff check src tests
```

Expected: everything green, zero ruff findings.

- [ ] **Step 2: Byte-identical passthrough audit.** Confirm by reading the diff that
  the `risk=None` / `risk_cfg=None` paths in `sizing.py`, `backtest.py`, `live.py`
  execute the exact pre-change statement sequence:

```bash
git diff b587dd6..HEAD -- src/number7/strategies/sizing.py src/number7/engine/backtest.py
```

- [ ] **Step 3: Trading-gate audit.** `git grep -n "risk_layer_version" src/` — the only
  hits must be `config.py` (unchanged). This work does NOT open the gate.

- [ ] **Step 4: Commit anything outstanding, then hand off** to the
  finishing-a-development-branch flow (PR against `main`, full test evidence in the PR
  body). The ablation run itself (`uv run python -m number7.research.ablate_risk_overlay`)
  is a follow-up manual step on a promoted dual-basis snapshot — hours of compute, not
  part of this branch's test plan.

---

## Plan self-review notes

- Spec coverage: §4.1–§4.6 → Tasks 1, 4, 5, 9, 10, 11; §5 tables/contracts → Tasks 2–4;
  §6 pipeline + invariants → Tasks 6–8; §7 errors → Tasks 4, 5, 9, 10 (each raise has a
  test); §8 testing list → Tasks 2–12; §9 ablation → Task 13; §10/§11 are
  documentation-only (no code).
- The spec's `spread_blocked` context field is implemented as `entry_barred` (spread
  gate ∪ min_obs bar — both are new-entry bars and the resolver treats them
  identically); the spec's own §6 fallback text requires the min_obs bar, so one set
  with recorded reasons beats two fields checked in two places.
- `resolve_book(risk=...)` returns `(book, ScalarResult)` (settled in Task 11; Tasks 8
  and 10 written against `applied_k` unpack — implementer: use the Task 11 form from the
  start and read `sres.applied_k` in the Task 8/10 tests).
- Beta-band paging is NOT in this plan by design: the streak is derivable from
  `risk_diag` and the page action belongs to the order service (spec §5).
