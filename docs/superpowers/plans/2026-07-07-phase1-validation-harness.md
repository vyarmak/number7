# Phase 1 — Validation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The statistical machinery that must exist before any strategy is trusted: a causal weekly-cadence backtest engine with the blueprint's timing contract, cost model, PSR/DSR + trials ledger with dedup/lineage, walk-forward runner, monkey/Monte-Carlo tests, golden-replay parity, look-ahead CI, known-answer calibration, equal-weight benchmark, lot/wash-sale accounting, and the Alpaca paper MOC probe.

**Architecture:** Everything reads Phase-0 snapshots (pinned by snapshot id). The engine is a causal loop over rebalance dates — each strategy sees only data ≤ signal date (T−1) and fills at T's close (blueprint §4.1 timing contract). `compute_live_targets()` is the exact function the Phase-2 order service will call; the golden-replay test pins engine ≡ live-path equality now. The trials ledger is DuckDB; DSR hurdles are tiered per blueprint §6 Gate 4.

**Tech Stack:** Python 3.12 (stdlib `statistics.NormalDist` — no scipy), pandas, numpy, duckdb, pydantic v2, exchange-calendars, pytest, alpaca-py (Task 14 only). Builds on Phase 0: `Settings`, `load_price_panel`, `close_matrix`, `load_membership`, `in_index_flags`, snapshot layout.

## Global Constraints

- Everything from the Phase-0 plan's Global Constraints carries over (paths, NY sessions, no network in tests except `vm`/`paper` marks).
- **Timing contract (blueprint §4.1, normative):** weights executed at close of rebalance date `T` are computed from data **≤ close of T−1** (the prior session). The engine enforces this by masking; the truncate-and-compare harness proves it.
- **Determinism:** every stochastic component (monkey test, bootstrap, random strategy) takes an explicit `seed`; identical seed ⇒ identical result.
- **Every backtest run is ledger-logged** (Task 9) with `code_sha`, `snapshot_id`, `param_hash`, metrics — no orphan runs.
- Returns are **log returns** in analysis, simple returns in equity compounding; costs in return space (fraction of traded notional).
- Add markers to `pyproject.toml` `[tool.pytest.ini_options]`: `markers = ["vm: ...", "paper: requires Alpaca paper account (run manually)"]`, `addopts = "-m 'not vm and not paper'"`.

## File Structure

```
src/number7/
├── engine/
│   ├── __init__.py
│   ├── schedule.py        # Task 1 — rebalance calendar + signal dates
│   ├── strategy.py        # Task 2 — Strategy protocol, manifest, reference strategies
│   ├── costs.py           # Task 3 — Corwin-Schultz + sqrt impact + commission
│   ├── backtest.py        # Task 4 — causal engine, equity, metrics
│   └── live.py            # Task 5 — compute_live_targets (Phase-2 contract)
├── validation/
│   ├── __init__.py
│   ├── causality.py       # Task 6 — truncate-and-compare harness
│   ├── dsr.py             # Task 8 — PSR / E[maxSR] / DSR / tiered hurdles
│   ├── walkforward.py     # Task 10 — frozen-protocol WF runner + WFE
│   ├── monkey.py          # Task 11 — matched random-strategy test
│   └── montecarlo.py      # Task 11 — block bootstrap: DD bands, Sharpe CI
├── research/
│   ├── __init__.py
│   ├── registry.py        # Task 9 — pre-registration schema (machine-readable)
│   └── ledger.py          # Task 9 — trials ledger (DuckDB), dedup/lineage
├── benchmarks/
│   ├── __init__.py
│   └── ew.py              # Task 12 — equal-weight index benchmark + Gate-6 comparator
├── execution/
│   ├── __init__.py
│   └── lots.py            # Task 13 — lot book, wash-sale detection/blackout
└── brokers/
    ├── __init__.py
    └── alpaca_probe.py    # Task 14 — paper MOC probe
tests/  (one test file per module, named test_<module>.py; fixtures extend conftest.py)
```

---

### Task 1: Rebalance schedule

**Files:**
- Create: `src/number7/engine/__init__.py`, `src/number7/engine/schedule.py`
- Test: `tests/test_schedule.py`

**Interfaces:**
- Produces: `sessions_between(start, end) -> pd.DatetimeIndex` (XNYS); `weekly_rebalances(sessions, weekday=1) -> pd.DatetimeIndex` (Tuesdays by default; if a week has no such weekday session, the week's first session after it); `signal_date(sessions, t) -> pd.Timestamp` (the session strictly before `t` — raises if `t` is the first session).

- [ ] **Step 1: Write the failing test** — `tests/test_schedule.py`

```python
import pandas as pd
import pytest

from number7.engine.schedule import sessions_between, signal_date, weekly_rebalances


def test_sessions_skip_holidays():
    s = sessions_between("2026-07-01", "2026-07-08")
    assert pd.Timestamp("2026-07-03") not in s          # July 4th observed
    assert pd.Timestamp("2026-07-06") in s


def test_weekly_rebalances_are_tuesdays():
    s = sessions_between("2026-06-01", "2026-06-30")
    rb = weekly_rebalances(s, weekday=1)
    assert all(d.weekday() == 1 for d in rb)
    assert len(rb) == 5                                  # 5 Tuesdays in June 2026


def test_signal_date_is_prior_session():
    s = sessions_between("2026-07-01", "2026-07-08")
    assert signal_date(s, pd.Timestamp("2026-07-06")) == pd.Timestamp("2026-07-02")
    with pytest.raises(ValueError):
        signal_date(s, s[0])
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_schedule.py -v` → FAIL (`No module named 'number7.engine'`)

- [ ] **Step 3: Implement** — `src/number7/engine/schedule.py`

```python
from __future__ import annotations

import exchange_calendars as xcals
import pandas as pd


def sessions_between(start: str, end: str) -> pd.DatetimeIndex:
    return xcals.get_calendar("XNYS").sessions_in_range(start, end)


def weekly_rebalances(sessions: pd.DatetimeIndex, weekday: int = 1) -> pd.DatetimeIndex:
    out = []
    for _, week in pd.Series(sessions, index=sessions).groupby(sessions.isocalendar().year * 100
                                                               + sessions.isocalendar().week):
        hit = [d for d in week if d.weekday() >= weekday]
        if hit:
            out.append(hit[0] if hit[0].weekday() == weekday or week[0].weekday() > weekday
                       else hit[0])
    return pd.DatetimeIndex([d for d in out])


def signal_date(sessions: pd.DatetimeIndex, t: pd.Timestamp) -> pd.Timestamp:
    i = sessions.get_loc(t)
    if i == 0:
        raise ValueError("no session before the first session")
    return sessions[i - 1]
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_schedule.py -v` → PASS (3)

- [ ] **Step 5: Commit** — `git add src/number7/engine tests/test_schedule.py && git commit -m "feat(phase1): XNYS rebalance schedule and signal dates"`

---

### Task 2: Strategy protocol + manifest + reference strategies

**Files:**
- Create: `src/number7/engine/strategy.py`
- Test: `tests/test_strategy.py`

**Interfaces:**
- Produces:
  - `PanelView` (frozen dataclass): `close: pd.DataFrame` (dates×symbols), `volume: pd.DataFrame`, `unadjusted_close: pd.DataFrame`, `in_index: pd.DataFrame` (bool), all **masked to dates ≤ view_end**; property `view_end`.
  - `StrategyManifest` (pydantic): `name: str`, `family: str`, `origin: Literal["human","llm"]`, `params: dict`, `reentry_blackout_days: int = 0`.
  - `Strategy` protocol: `manifest: StrategyManifest`; `target_weights(view: PanelView) -> pd.Series` (index=symbols, values ≥ 0 summing ≤ 1.0; cash is the remainder).
  - Reference implementations: `RandomTopN(n, seed)` (uniform-random ranking of in-index symbols at `view_end`, equal-weight top n — the null strategy) and `LookaheadTrap(n)` (deliberately peeks: ranks by the *next* session's return — exists to prove the causality harness catches it; guarded so it can only run under tests).

- [ ] **Step 1: Write the failing test** — `tests/test_strategy.py`

```python
import numpy as np
import pandas as pd

from number7.engine.strategy import PanelView, RandomTopN, StrategyManifest


def _view() -> PanelView:
    dates = pd.date_range("2026-06-01", periods=10, freq="B")
    close = pd.DataFrame(np.linspace(100, 110, 10)[:, None] * [1, 2, 3],
                         index=dates, columns=["A", "B", "C"])
    flags = pd.DataFrame(True, index=dates, columns=["A", "B", "C"])
    flags.loc[:, "C"] = False                             # C not in index
    return PanelView(close=close, volume=close * 0 + 1e6,
                     unadjusted_close=close, in_index=flags)


def test_random_topn_weights_are_valid_and_seeded():
    v = _view()
    s1, s2 = RandomTopN(n=2, seed=7), RandomTopN(n=2, seed=7)
    w1, w2 = s1.target_weights(v), s2.target_weights(v)
    pd.testing.assert_series_equal(w1, w2)                # deterministic under seed
    assert (w1 >= 0).all() and w1.sum() <= 1.0 + 1e-9
    assert "C" not in w1[w1 > 0].index                    # never buys non-members


def test_manifest_roundtrip():
    m = StrategyManifest(name="rand", family="null", origin="human", params={"n": 2})
    assert m.reentry_blackout_days == 0
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_strategy.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/engine/strategy.py`

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

import numpy as np
import pandas as pd
from pydantic import BaseModel


@dataclass(frozen=True)
class PanelView:
    close: pd.DataFrame
    volume: pd.DataFrame
    unadjusted_close: pd.DataFrame
    in_index: pd.DataFrame

    @property
    def view_end(self) -> pd.Timestamp:
        return self.close.index[-1]

    def masked_to(self, end: pd.Timestamp) -> "PanelView":
        return PanelView(*(df.loc[:end] for df in
                           (self.close, self.volume, self.unadjusted_close, self.in_index)))


class StrategyManifest(BaseModel):
    name: str
    family: str
    origin: Literal["human", "llm"]
    params: dict
    reentry_blackout_days: int = 0


class Strategy(Protocol):
    manifest: StrategyManifest

    def target_weights(self, view: PanelView) -> pd.Series: ...


class RandomTopN:
    """Null strategy: random ranking, equal-weight top n members. Calibration fixture."""

    def __init__(self, n: int, seed: int) -> None:
        self.manifest = StrategyManifest(name=f"random_top{n}", family="null",
                                         origin="human", params={"n": n, "seed": seed})
        self._rng = np.random.default_rng(seed)
        self.n = n

    def target_weights(self, view: PanelView) -> pd.Series:
        members = view.in_index.iloc[-1]
        candidates = list(members.index[members])
        picks = list(self._rng.permutation(candidates))[: self.n]
        w = pd.Series(0.0, index=view.close.columns)
        if picks:
            w[picks] = 1.0 / self.n
        return w


class LookaheadTrap:
    """DELIBERATELY CHEATS (ranks by the next session's return). Only for harness tests."""

    def __init__(self, n: int, full_close: pd.DataFrame) -> None:
        self.manifest = StrategyManifest(name="lookahead_trap", family="trap",
                                         origin="human", params={"n": n})
        self.n, self._full_close = n, full_close

    def target_weights(self, view: PanelView) -> pd.Series:
        t = view.view_end
        future = self._full_close.loc[self._full_close.index > t]
        w = pd.Series(0.0, index=view.close.columns)
        if len(future) == 0:
            return w
        nxt = np.log(future.iloc[0] / view.close.loc[t]).fillna(-np.inf)
        picks = nxt.nlargest(self.n).index
        w[picks] = 1.0 / self.n
        return w
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_strategy.py -v` → PASS (2)

- [ ] **Step 5: Commit** — `git add src/number7/engine/strategy.py tests/test_strategy.py && git commit -m "feat(phase1): strategy protocol, manifest, null and trap fixtures"`

---

### Task 3: Cost model

**Files:**
- Create: `src/number7/engine/costs.py`
- Test: `tests/test_costs.py`

**Interfaces:**
- Produces: `corwin_schultz(high: pd.Series, low: pd.Series, window: int = 21) -> pd.Series` (rolling mean 2-day CS spread estimate, floored at 0); `impact_cost(q_over_adv: float, daily_sigma: float) -> float` = `(2/3)·σ·√(Q/ADV)` (KB-09); `CostModel` (pydantic: `commission_bps: float = 0.0`, `min_half_spread_bps: float = 2.0`) with `one_way_cost(spread_est: float, q_over_adv: float, sigma: float) -> float` = commission + max(spread/2, floor) + impact, all in return space.

- [ ] **Step 1: Write the failing test** — `tests/test_costs.py`

```python
import numpy as np
import pandas as pd
import pytest

from number7.engine.costs import CostModel, corwin_schultz, impact_cost


def test_corwin_schultz_hand_value():
    # H/L = e^0.02 every day and across the 2-day span -> S ≈ 0.02004 (hand-derived)
    n = 40
    close = pd.Series(100.0, index=pd.date_range("2026-01-01", periods=n, freq="B"))
    high, low = close * np.exp(0.02), close
    s = corwin_schultz(high, low, window=21)
    assert s.iloc[-1] == pytest.approx(0.02004, abs=1e-3)


def test_corwin_schultz_zero_range_is_zero():
    idx = pd.date_range("2026-01-01", periods=30, freq="B")
    s = corwin_schultz(pd.Series(100.0, index=idx), pd.Series(100.0, index=idx))
    assert s.iloc[-1] == pytest.approx(0.0, abs=1e-12)


def test_impact_hand_value():
    assert impact_cost(0.01, 0.02) == pytest.approx((2 / 3) * 0.02 * 0.1, rel=1e-9)


def test_one_way_cost_floors_spread():
    cm = CostModel(commission_bps=0.0, min_half_spread_bps=2.0)
    c = cm.one_way_cost(spread_est=0.0, q_over_adv=0.0, sigma=0.02)
    assert c == pytest.approx(0.0002, rel=1e-9)          # floor binds
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_costs.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/engine/costs.py`

```python
from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel

_DEN = 3 - 2 * np.sqrt(2.0)


def corwin_schultz(high: pd.Series, low: pd.Series, window: int = 21) -> pd.Series:
    """Corwin-Schultz (2012) 2-day high-low spread estimator, rolling-averaged."""
    with np.errstate(divide="ignore", invalid="ignore"):
        hl = np.log(high / low) ** 2
        beta = hl + hl.shift(-1)
        h2 = pd.concat([high, high.shift(-1)], axis=1).max(axis=1)
        l2 = pd.concat([low, low.shift(-1)], axis=1).min(axis=1)
        gamma = np.log(h2 / l2) ** 2
        alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / _DEN - np.sqrt(gamma / _DEN)
        s = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return s.clip(lower=0).rolling(window, min_periods=5).mean()


def impact_cost(q_over_adv: float, daily_sigma: float) -> float:
    return (2.0 / 3.0) * daily_sigma * float(np.sqrt(max(q_over_adv, 0.0)))


class CostModel(BaseModel):
    commission_bps: float = 0.0
    min_half_spread_bps: float = 2.0

    def one_way_cost(self, spread_est: float, q_over_adv: float, sigma: float) -> float:
        half_spread = max(spread_est / 2.0, self.min_half_spread_bps / 1e4)
        return self.commission_bps / 1e4 + half_spread + impact_cost(q_over_adv, sigma)
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_costs.py -v` → PASS (4)

- [ ] **Step 5: Commit** — `git add src/number7/engine/costs.py tests/test_costs.py && git commit -m "feat(phase1): corwin-schultz + sqrt-impact cost model"`

---

### Task 4: Causal backtest engine

**Files:**
- Create: `src/number7/engine/backtest.py`
- Test: `tests/test_backtest.py`

**Interfaces:**
- Consumes: `PanelView`/`Strategy` (Task 2), `CostModel` (Task 3), `weekly_rebalances`/`signal_date` (Task 1).
- Produces:
  - `BacktestResult` (dataclass): `equity: pd.Series` (indexed by session), `weights: pd.DataFrame` (rebalance dates × symbols — the decided targets), `turnover: pd.Series`, `costs: pd.Series`, `rebalance_dates: pd.DatetimeIndex`.
  - `run_backtest(strategy, panel: PanelView, rebalance_dates, cost_model, initial=1.0) -> BacktestResult`.
  - `summary(result) -> dict` with keys `cagr, sharpe, sortino, max_dd, profit_factor, hit_rate, n_rebalances, avg_turnover` (Sharpe = ann. mean/std of daily log returns ×√252, rf=0).
- **Timing semantics (normative, tested):** for rebalance date `T`, the strategy is called with `panel.masked_to(signal_date(sessions, T))`; the book holds the *previous* weights through close of `T`, pays `Σ|Δw| × one_way_cost` at `T`'s close, then holds new weights until the next rebalance. Weights drift with returns between rebalances (KB-11 §3a); turnover is measured against **drifted** weights.

- [ ] **Step 1: Write the failing test** — `tests/test_backtest.py` (hand-computed toy)

```python
import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, StrategyManifest


class AllInA:
    manifest = StrategyManifest(name="all_in_a", family="test", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.close.columns)
        w["A"] = 1.0
        return w


def _panel(n=15):
    dates = pd.date_range("2026-01-05", periods=n, freq="B")     # Mon start, no holidays
    a = 100 * np.cumprod(np.full(n, 1.01))                       # A: +1%/day
    b = np.full(n, 50.0)                                         # B: flat
    close = pd.DataFrame({"A": a, "B": b}, index=dates)
    ones = pd.DataFrame(True, index=dates, columns=["A", "B"])
    return PanelView(close=close, volume=close * 0 + 1e9,
                     unadjusted_close=close, in_index=ones)


def test_engine_timing_and_compounding():
    panel = _panel()
    rb = pd.DatetimeIndex([panel.close.index[2], panel.close.index[7]])   # two rebalances
    res = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    # Before first rebalance: flat (cash). After close of rb[0]: full A exposure.
    assert res.equity.loc[rb[0]] == pytest.approx(1.0)                    # nothing earned yet
    expected = 1.01 ** (len(panel.close.loc[rb[0]:]) - 1)                 # A's +1% dailies after T
    assert res.equity.iloc[-1] == pytest.approx(expected, rel=1e-9)
    # Turnover: 1.0 at first rebalance (cash->A), 0.0 at second (already all A, no drift vs A-only)
    assert res.turnover.loc[rb[0]] == pytest.approx(1.0)
    assert res.turnover.loc[rb[1]] == pytest.approx(0.0, abs=1e-12)


def test_costs_reduce_equity():
    panel = _panel()
    rb = pd.DatetimeIndex([panel.close.index[2]])
    free = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    paid = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=10.0))
    assert paid.equity.iloc[-1] < free.equity.iloc[-1]
    assert paid.costs.loc[rb[0]] == pytest.approx(10.0 / 1e4, rel=1e-6)


def test_summary_keys():
    panel = _panel()
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([panel.close.index[2]]),
                       CostModel())
    s = summary(res)
    assert set(s) == {"cagr", "sharpe", "sortino", "max_dd", "profit_factor",
                      "hit_rate", "n_rebalances", "avg_turnover"}
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_backtest.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/engine/backtest.py`

```python
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from number7.engine.costs import CostModel, corwin_schultz
from number7.engine.schedule import signal_date
from number7.engine.strategy import PanelView, Strategy


@dataclass
class BacktestResult:
    equity: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series
    rebalance_dates: pd.DatetimeIndex


def _one_way(cost_model: CostModel, panel: PanelView, t: pd.Timestamp,
             sym: str, dw: float, equity: float) -> float:
    hi = panel.close[sym] * 1.0  # spreads from adjusted OHLC unavailable in view: use vol floor
    sigma = float(np.log(panel.close[sym]).diff().loc[:t].tail(63).std() or 0.0)
    adv = float((panel.unadjusted_close[sym] * panel.volume[sym]).loc[:t].tail(20).mean() or np.inf)
    q_over_adv = 0.0 if not np.isfinite(adv) or adv <= 0 else abs(dw) * equity / adv
    return cost_model.one_way_cost(spread_est=0.0, q_over_adv=q_over_adv, sigma=sigma)


def run_backtest(strategy: Strategy, panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                 cost_model: CostModel, initial: float = 1.0) -> BacktestResult:
    sessions = panel.close.index
    rets = panel.close.pct_change().fillna(0.0)
    equity = pd.Series(np.nan, index=sessions, dtype=float)
    decided = {}
    turnover, costs = {}, {}

    w = pd.Series(0.0, index=panel.close.columns)   # start in cash
    eq = initial
    rb = set(rebalance_dates)

    for t in sessions:
        eq *= float(1.0 + (w * rets.loc[t]).sum())          # earn today with yesterday's book
        if len(w[w > 0]):                                    # drift weights with returns
            grown = w * (1.0 + rets.loc[t])
            port = float(grown.sum() + (1.0 - w.sum()))      # cash leg grows at 0
            w = grown / port
        if t in rb:
            view = panel.masked_to(signal_date(sessions, t))
            target = strategy.target_weights(view).reindex(w.index).fillna(0.0)
            dw = (target - w).abs()
            tw = float(dw.sum())
            c = sum(_one_way(cost_model, panel, t, s, dw[s], eq) * dw[s] for s in dw.index[dw > 0])
            eq *= float(1.0 - c)
            turnover[t], costs[t], decided[t] = tw, c, target
            w = target.copy()
        equity.loc[t] = eq

    return BacktestResult(
        equity=equity,
        weights=pd.DataFrame(decided).T if decided else pd.DataFrame(columns=panel.close.columns),
        turnover=pd.Series(turnover, dtype=float),
        costs=pd.Series(costs, dtype=float),
        rebalance_dates=pd.DatetimeIndex(sorted(rb)),
    )


def summary(result: BacktestResult) -> dict:
    eq = result.equity.dropna()
    r = np.log(eq).diff().dropna()
    years = max(len(r) / 252.0, 1e-9)
    ann = float(r.mean() * 252)
    vol = float(r.std(ddof=0) * np.sqrt(252))
    downside = float(r[r < 0].std(ddof=0) * np.sqrt(252)) or np.nan
    dd = (eq / eq.cummax() - 1.0).min()
    gains, losses = float(r[r > 0].sum()), float(-r[r < 0].sum())
    return {
        "cagr": float(eq.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0,
        "sharpe": ann / vol if vol > 0 else 0.0,
        "sortino": ann / downside if downside and downside > 0 else 0.0,
        "max_dd": float(dd),
        "profit_factor": gains / losses if losses > 0 else np.inf,
        "hit_rate": float((r > 0).mean()),
        "n_rebalances": int(len(result.rebalance_dates)),
        "avg_turnover": float(result.turnover.mean()) if len(result.turnover) else 0.0,
    }
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_backtest.py -v` → PASS (3)

- [ ] **Step 5: Commit** — `git add src/number7/engine/backtest.py tests/test_backtest.py && git commit -m "feat(phase1): causal weekly backtest engine with drift-aware turnover"`

---

### Task 5: Live-target contract + golden-replay parity

**Files:**
- Create: `src/number7/engine/live.py`
- Test: `tests/test_live_parity.py`

**Interfaces:**
- Consumes: Phase-0 `load_price_panel`, `load_membership`, `in_index_flags`; Tasks 1–2, 4.
- Produces: `build_panel(snapshot_root, start=None) -> PanelView` (assembles close/volume/unadjusted/in_index matrices from a snapshot); `compute_live_targets(strategy, panel, asof: pd.Timestamp) -> pd.Series` — **the exact function the Phase-2 order service calls**: masks the panel to `signal_date(sessions, asof)` and returns the strategy's weights for execution at `asof`'s close.
- Golden replay: for every rebalance date, `compute_live_targets` must equal the engine's decided weights bit-for-bit.

- [ ] **Step 1: Write the failing test** — `tests/test_live_parity.py`

```python
import pandas as pd

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.live import build_panel, compute_live_targets
from number7.engine.strategy import RandomTopN


def test_golden_replay_engine_equals_live_path(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.close.index[2], panel.close.index[3]])
    strat_engine, strat_live = RandomTopN(n=1, seed=3), RandomTopN(n=1, seed=3)
    res = run_backtest(strat_engine, panel, rb, CostModel())
    for t in rb:
        live = compute_live_targets(strat_live, panel, asof=t)
        pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_live_parity.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/engine/live.py`

```python
from __future__ import annotations

from pathlib import Path

import pandas as pd

from number7.data.store import load_price_panel
from number7.data.universe import in_index_flags, load_membership
from number7.engine.schedule import signal_date
from number7.engine.strategy import PanelView, Strategy


def build_panel(snapshot_root: Path, start: str | None = None) -> PanelView:
    tidy = load_price_panel(snapshot_root, start=start)
    piv = lambda col: tidy.pivot(index="date", columns="symbol", values=col).sort_index()
    close = piv("close")
    membership = load_membership(snapshot_root)
    flags = in_index_flags(membership, list(close.columns), close.index)
    extra = set(close.columns) - set(membership["symbol"])   # e.g. SPY: always tradable
    flags.loc[:, sorted(extra)] = True
    return PanelView(close=close, volume=piv("volume"),
                     unadjusted_close=piv("unadjusted_close"), in_index=flags)


def compute_live_targets(strategy: Strategy, panel: PanelView, asof: pd.Timestamp) -> pd.Series:
    """THE Phase-2 order-service entry point: weights to execute at `asof`'s close,
    decided strictly from data <= the prior session (blueprint §4.1 timing contract)."""
    view = panel.masked_to(signal_date(panel.close.index, asof))
    return strategy.target_weights(view).reindex(panel.close.columns).fillna(0.0)
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_live_parity.py -v` → PASS (1)

*(Note: `RandomTopN` instances share a seed but consume RNG per call — the test constructs two fresh instances and calls each once per rebalance in the same order, so draws align. The engine calls `target_weights` exactly once per rebalance date; `compute_live_targets` likewise.)*

- [ ] **Step 5: Commit** — `git add src/number7/engine/live.py tests/test_live_parity.py && git commit -m "feat(phase1): live-target contract with golden-replay parity test"`

---

### Task 6: Causality harness (truncate-and-compare) + trap detection

**Files:**
- Create: `src/number7/validation/__init__.py`, `src/number7/validation/causality.py`
- Test: `tests/test_causality.py`

**Interfaces:**
- Consumes: Tasks 1–5.
- Produces: `causality_violations(strategy_factory, panel, rebalance_dates, truncate_last_n=5) -> list[pd.Timestamp]` — runs the strategy on the full panel and on a panel truncated by `truncate_last_n` sessions; returns rebalance dates (in the common range) whose decided weights differ. Empty list = causal. `strategy_factory` is a zero-arg callable returning a *fresh* strategy (stateful strategies must be re-instantiated per run). This check runs in CI for every strategy PR (blueprint Gate 1).

- [ ] **Step 1: Write the failing test** — `tests/test_causality.py`

```python
import pandas as pd

from number7.engine.live import build_panel
from number7.engine.strategy import LookaheadTrap, RandomTopN
from number7.validation.causality import causality_violations


def test_causal_strategy_is_clean(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.close.index[1], panel.close.index[2]])
    v = causality_violations(lambda: RandomTopN(n=1, seed=5), panel, rb, truncate_last_n=1)
    assert v == []


def test_lookahead_trap_is_caught(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.close.index[1], panel.close.index[2]])
    v = causality_violations(lambda: LookaheadTrap(n=1, full_close=panel.close),
                             panel, rb, truncate_last_n=1)
    assert len(v) >= 1                                     # the trap MUST be caught
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_causality.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/validation/causality.py`

```python
from __future__ import annotations

from typing import Callable

import pandas as pd

from number7.engine.live import compute_live_targets
from number7.engine.strategy import PanelView, Strategy


def causality_violations(strategy_factory: Callable[[], Strategy], panel: PanelView,
                         rebalance_dates: pd.DatetimeIndex,
                         truncate_last_n: int = 5) -> list[pd.Timestamp]:
    cut = panel.close.index[-(truncate_last_n + 1)]
    truncated = panel.masked_to(cut)
    common = [t for t in rebalance_dates if t <= cut]
    full_s, trunc_s = strategy_factory(), strategy_factory()
    bad: list[pd.Timestamp] = []
    for t in common:
        w_full = compute_live_targets(full_s, panel, asof=t)
        w_trunc = compute_live_targets(trunc_s, truncated, asof=t).reindex(w_full.index).fillna(0.0)
        if not w_full.round(12).equals(w_trunc.round(12)):
            bad.append(t)
    return bad
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_causality.py -v` → PASS (2)

- [ ] **Step 5: Commit** — `git add src/number7/validation tests/test_causality.py && git commit -m "feat(phase1): truncate-and-compare causality harness catches look-ahead"`

---

### Task 7: Known-answer calibration — the null strategy scores ~zero

**Files:**
- Test: `tests/test_calibration.py` (no new source — this validates the harness itself; blueprint Phase-1 success criterion)

- [ ] **Step 1: Write the test**

```python
import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import PanelView, RandomTopN


def _synthetic_panel(n_days=756, n_sym=30, seed=11) -> PanelView:
    """Zero-drift GBM universe: no strategy should make money here pre-cost."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_days, freq="B")
    rets = rng.normal(0.0, 0.01, size=(n_days, n_sym))
    close = pd.DataFrame(100 * np.exp(np.cumsum(rets, axis=0)), index=dates,
                         columns=[f"S{i:02d}" for i in range(n_sym)])
    ones = pd.DataFrame(True, index=dates, columns=close.columns)
    return PanelView(close=close, volume=close * 0 + 1e9, unadjusted_close=close, in_index=ones)


def test_null_strategy_earns_nothing_pre_cost():
    panel = _synthetic_panel()
    rb = weekly_rebalances(panel.close.index)
    cagrs = []
    for seed in range(8):
        res = run_backtest(RandomTopN(n=5, seed=seed), panel, rb,
                           CostModel(commission_bps=0.0, min_half_spread_bps=0.0))
        cagrs.append(summary(res)["cagr"])
    mean_cagr = float(np.mean(cagrs))
    assert abs(mean_cagr) < 0.05          # ~zero edge on zero-drift data
    assert 0.35 < float(np.mean([summary(run_backtest(RandomTopN(n=5, seed=s), panel, rb,
                                 CostModel(min_half_spread_bps=0.0))).get("hit_rate")
                                 for s in range(3)])) < 0.65
```

- [ ] **Step 2: Run** — `uv run pytest tests/test_calibration.py -v`
Expected: PASS (harness produces ~zero for a zero-edge world — if this fails, the engine leaks or mis-compounds; STOP and fix before proceeding).

- [ ] **Step 3: Commit** — `git add tests/test_calibration.py && git commit -m "test(phase1): known-answer calibration - null strategy scores zero"`

---

### Task 8: PSR / E[maxSR] / DSR + tiered hurdles

**Files:**
- Create: `src/number7/validation/dsr.py`
- Test: `tests/test_dsr.py`

**Interfaces:**
- Produces (KB-07 §4a, Bailey–López de Prado — exact formulas):
  - `psr(sr_obs, n_obs, skew, kurt, sr_benchmark=0.0) -> float` = `Φ[(SR−SR*)·√(n−1) / √(1 − γ₃·SR + ((γ₄−1)/4)·SR²)]` (per-period SR, not annualized).
  - `expected_max_sr(n_trials, var_trials) -> float` = `√V·[(1−γe)·Φ⁻¹(1−1/K) + γe·Φ⁻¹(1−1/(K·e))]`, `γe = 0.5772156649`.
  - `dsr(sr_obs, n_obs, skew, kurt, n_trials, var_trials) -> float` = `psr(..., sr_benchmark=expected_max_sr(...))`.
  - `dsr_hurdle(n_effective_trials, origin) -> float` — 0.98 if `n_effective_trials < 15` else 0.95; `origin == "llm"` ⇒ always 0.98 (blueprint Gate 4).

- [ ] **Step 1: Write the failing test** — `tests/test_dsr.py`

```python
import pytest

from number7.validation.dsr import dsr, dsr_hurdle, expected_max_sr, psr


def test_expected_max_sr_kb_textbook_value():
    # KB-07 §4a: 1,000 zero-edge trials at V=1 -> expected max Sharpe ≈ 3.26
    assert expected_max_sr(1000, 1.0) == pytest.approx(3.26, abs=0.02)


def test_psr_hand_value():
    # SR=0.1/period, 252 obs, gaussian returns -> z = 0.1*sqrt(251)/sqrt(1+0.005) ≈ 1.5805
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
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_dsr.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/validation/dsr.py`

```python
from __future__ import annotations

import math
from statistics import NormalDist

_N = NormalDist()
_EULER = 0.5772156649015329


def psr(sr_obs: float, n_obs: int, skew: float, kurt: float,
        sr_benchmark: float = 0.0) -> float:
    """Probabilistic Sharpe Ratio (Bailey & Lopez de Prado). Per-period SR."""
    denom = math.sqrt(max(1.0 - skew * sr_obs + ((kurt - 1.0) / 4.0) * sr_obs ** 2, 1e-12))
    z = (sr_obs - sr_benchmark) * math.sqrt(n_obs - 1) / denom
    return _N.cdf(z)


def expected_max_sr(n_trials: int, var_trials: float) -> float:
    """E[max SR] under the null across K trials ('False Strategy' theorem)."""
    k = max(int(n_trials), 1)
    if k == 1:
        return 0.0
    a = _N.inv_cdf(1.0 - 1.0 / k)
    b = _N.inv_cdf(1.0 - 1.0 / (k * math.e))
    return math.sqrt(max(var_trials, 0.0)) * ((1.0 - _EULER) * a + _EULER * b)


def dsr(sr_obs: float, n_obs: int, skew: float, kurt: float,
        n_trials: int, var_trials: float) -> float:
    return psr(sr_obs, n_obs, skew, kurt,
               sr_benchmark=expected_max_sr(n_trials, var_trials))


def dsr_hurdle(n_effective_trials: int, origin: str) -> float:
    if origin == "llm" or n_effective_trials < 15:
        return 0.98
    return 0.95
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_dsr.py -v` → PASS (5)

- [ ] **Step 5: Commit** — `git add src/number7/validation/dsr.py tests/test_dsr.py && git commit -m "feat(phase1): PSR/DSR with expected-max-SR hurdle and origin tiers"`

---

### Task 9: Pre-registration schema + trials ledger

**Files:**
- Create: `src/number7/research/__init__.py`, `src/number7/research/registry.py`, `src/number7/research/ledger.py`
- Test: `tests/test_ledger.py`

**Interfaces:**
- Produces:
  - `PreRegistration` (pydantic, the machine-readable hypothesis — blueprint §5): `family: str`, `origin: Literal["human","llm"]`, `mechanism: str` (≥ 40 chars — a sentence, not a tag), `citations: list[str]` (≥ 1), `expected_effect: str`, `falsification: str`, `param_space: dict[str, list]` (explicit finite grid), `search_space_size` (computed property: product of grid lengths).
  - `Ledger` (DuckDB at `research/ledger.duckdb`): `register(prereg) -> int` (family row + declared search space; **rejects** a registration whose `param_hash` matches a scrapped/failed registration in the same family — the tweak-and-retest guard); `log_run(reg_id, code_sha, snapshot_id, params, metrics: dict) -> int`; `family_trials(family) -> int` (runs + declared-space penalty = `max(runs, search_space_size)`); `var_of_trial_sharpes(family) -> float`; `scrap(reg_id)`.
  - `param_hash(params: dict) -> str` (sha256 of canonical JSON).

- [ ] **Step 1: Write the failing test** — `tests/test_ledger.py`

```python
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
                params={"lookback": 90, "top_n": 25}, metrics={"sharpe": 0.8, "n_obs": 500})
    assert led.family_trials("momentum_v1") == 6          # declared space dominates 1 run
    for lb in (60, 90, 120):
        for n in (20, 25):
            led.log_run(reg, code_sha="abc", snapshot_id="2026-07-02",
                        params={"lookback": lb, "top_n": n}, metrics={"sharpe": 0.1 * n / 20,
                                                                     "n_obs": 500})
    assert led.family_trials("momentum_v1") == 7          # 7 runs > declared 6
    assert led.var_of_trial_sharpes("momentum_v1") > 0


def test_scrapped_params_cannot_reenter(tmp_path):
    led = Ledger(tmp_path / "ledger.duckdb")
    reg = led.register(_prereg())
    led.scrap(reg)
    with pytest.raises(ValueError, match="scrapped"):
        led.register(_prereg())                            # same family+param space -> rejected


def test_param_hash_is_order_insensitive():
    assert param_hash({"a": 1, "b": 2}) == param_hash({"b": 2, "a": 1})
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_ledger.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/research/registry.py`

```python
from __future__ import annotations

import math
from typing import Literal

from pydantic import BaseModel, Field


class PreRegistration(BaseModel):
    family: str
    origin: Literal["human", "llm"]
    mechanism: str = Field(min_length=40)
    citations: list[str] = Field(min_length=1)
    expected_effect: str
    falsification: str
    param_space: dict[str, list]

    @property
    def search_space_size(self) -> int:
        return math.prod(len(v) for v in self.param_space.values()) or 1
```

— `src/number7/research/ledger.py`

```python
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from number7.research.registry import PreRegistration

_SCHEMA = """
create sequence if not exists reg_seq; create sequence if not exists run_seq;
create table if not exists registrations(
  reg_id bigint primary key, family text, origin text, mechanism text,
  param_space_hash text, search_space_size int, status text default 'registered',
  created_at timestamp default current_timestamp);
create table if not exists runs(
  run_id bigint primary key, reg_id bigint, code_sha text, snapshot_id text,
  param_hash text, params json, sharpe double, n_obs int, metrics json,
  created_at timestamp default current_timestamp);
"""


def param_hash(params: dict) -> str:
    return hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()


class Ledger:
    def __init__(self, path: Path) -> None:
        self._con = duckdb.connect(str(path))
        for stmt in _SCHEMA.strip().split(";"):
            if stmt.strip():
                self._con.execute(stmt)

    def register(self, prereg: PreRegistration) -> int:
        space_hash = param_hash(prereg.param_space)
        dup = self._con.execute(
            "select count(*) from registrations where family=? and param_space_hash=? "
            "and status='scrapped'", [prereg.family, space_hash]).fetchone()[0]
        if dup:
            raise ValueError(f"param space was scrapped in family {prereg.family!r}; "
                             "re-entry requires human sign-off (new family or amended space)")
        reg_id = self._con.execute("select nextval('reg_seq')").fetchone()[0]
        self._con.execute(
            "insert into registrations(reg_id, family, origin, mechanism, param_space_hash, "
            "search_space_size) values (?,?,?,?,?,?)",
            [reg_id, prereg.family, prereg.origin, prereg.mechanism, space_hash,
             prereg.search_space_size])
        return reg_id

    def log_run(self, reg_id: int, code_sha: str, snapshot_id: str,
                params: dict, metrics: dict) -> int:
        run_id = self._con.execute("select nextval('run_seq')").fetchone()[0]
        self._con.execute(
            "insert into runs values (?,?,?,?,?,?,?,?,?, current_timestamp)",
            [run_id, reg_id, code_sha, snapshot_id, param_hash(params), json.dumps(params),
             float(metrics.get("sharpe", 0.0)), int(metrics.get("n_obs", 0)),
             json.dumps(metrics)])
        return run_id

    def family_trials(self, family: str) -> int:
        row = self._con.execute(
            "select coalesce(sum(r.search_space_size),0), count(x.run_id) "
            "from registrations r left join runs x on x.reg_id=r.reg_id "
            "where r.family=?", [family]).fetchone()
        declared = self._con.execute(
            "select coalesce(sum(search_space_size),0) from registrations where family=?",
            [family]).fetchone()[0]
        runs = self._con.execute(
            "select count(*) from runs x join registrations r on r.reg_id=x.reg_id "
            "where r.family=?", [family]).fetchone()[0]
        return max(int(declared), int(runs))

    def var_of_trial_sharpes(self, family: str) -> float:
        v = self._con.execute(
            "select var_pop(x.sharpe) from runs x join registrations r on r.reg_id=x.reg_id "
            "where r.family=?", [family]).fetchone()[0]
        return float(v or 0.0)

    def scrap(self, reg_id: int) -> None:
        self._con.execute("update registrations set status='scrapped' where reg_id=?", [reg_id])
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_ledger.py -v` → PASS (4)

- [ ] **Step 5: Commit** — `git add src/number7/research tests/test_ledger.py && git commit -m "feat(phase1): pre-registration schema and trials ledger with scrap guard"`

---

### Task 10: Walk-forward runner (frozen protocol)

**Files:**
- Create: `src/number7/validation/walkforward.py`
- Test: `tests/test_walkforward.py`

**Interfaces:**
- Consumes: engine (Task 4), schedule (Task 1).
- Produces: `WFProtocol` (frozen pydantic: `train_years: int = 5`, `test_months: int = 12`, `step_months: int = 12`, `min_windows: int = 10`, `wfe_floor: float = 0.5`); `walk_forward(strategy_factory, panel, protocol, cost_model) -> WFReport` where `WFReport` has `windows: list[dict]` (each: train span, test span, is_annual_profit, oos_annual_profit), `wfe: float` (**annualized OOS net log-profit ÷ annualized IS net log-profit** — Tomasini/Pardo definition, blueprint Gate 3), `stitched_oos_equity: pd.Series`, `passes(protocol) -> bool` (≥ min_windows and wfe ≥ floor and stitched OOS ends above start).
- Note: strategies here are rule-based (params fixed by pre-registration) — "train" = the burn-in history the signal needs; per-window re-fitting enters only when a strategy family declares fittable params (the protocol object is where that stays frozen).

- [ ] **Step 1: Write the failing test** — `tests/test_walkforward.py`

```python
import numpy as np
import pandas as pd

from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, StrategyManifest
from number7.validation.walkforward import WFProtocol, walk_forward


class AlwaysLong:
    manifest = StrategyManifest(name="long", family="test", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.close.columns)
        w[view.close.columns[0]] = 1.0
        return w


def _drift_panel(years=8, mu=0.0004):
    n = int(252 * years)
    dates = pd.date_range("2016-01-04", periods=n, freq="B")
    close = pd.DataFrame({"A": 100 * np.exp(np.cumsum(np.full(n, mu)))}, index=dates)
    ones = pd.DataFrame(True, index=dates, columns=["A"])
    return PanelView(close=close, volume=close * 0 + 1e9, unadjusted_close=close, in_index=ones)


def test_walk_forward_on_steady_drift():
    protocol = WFProtocol(train_years=3, test_months=6, step_months=6, min_windows=8)
    report = walk_forward(lambda: AlwaysLong(), _drift_panel(), protocol,
                          CostModel(min_half_spread_bps=0.0))
    assert len(report.windows) >= 8
    assert report.wfe == pytest.approx(1.0, abs=0.15)      # same drift IS and OOS
    assert report.passes(protocol)


import pytest  # noqa: E402  (used above)
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_walkforward.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/validation/walkforward.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
from pydantic import BaseModel

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import PanelView, Strategy


class WFProtocol(BaseModel):
    model_config = {"frozen": True}
    train_years: int = 5
    test_months: int = 12
    step_months: int = 12
    min_windows: int = 10
    wfe_floor: float = 0.5


@dataclass
class WFReport:
    windows: list[dict] = field(default_factory=list)
    wfe: float = 0.0
    stitched_oos_equity: pd.Series | None = None

    def passes(self, protocol: WFProtocol) -> bool:
        return (len(self.windows) >= protocol.min_windows
                and self.wfe >= protocol.wfe_floor
                and self.stitched_oos_equity is not None
                and float(self.stitched_oos_equity.iloc[-1]) > float(self.stitched_oos_equity.iloc[0]))


def _annual_log_profit(equity: pd.Series) -> float:
    lp = float(np.log(equity.iloc[-1] / equity.iloc[0]))
    years = max(len(equity) / 252.0, 1e-9)
    return lp / years


def walk_forward(strategy_factory: Callable[[], Strategy], panel: PanelView,
                 protocol: WFProtocol, cost_model: CostModel) -> WFReport:
    sessions = panel.close.index
    report = WFReport()
    oos_pieces: list[pd.Series] = []
    start = sessions[0]
    while True:
        train_end = start + pd.DateOffset(years=protocol.train_years)
        test_end = train_end + pd.DateOffset(months=protocol.test_months)
        if test_end > sessions[-1]:
            break
        is_view = panel.masked_to(sessions[sessions <= train_end][-1])
        is_sessions = is_view.close.index[is_view.close.index >= start]
        is_res = run_backtest(strategy_factory(), is_view, weekly_rebalances(is_sessions),
                              cost_model)
        oos_view = panel.masked_to(sessions[sessions <= test_end][-1])
        oos_sessions = oos_view.close.index[oos_view.close.index > train_end]
        oos_res = run_backtest(strategy_factory(), oos_view, weekly_rebalances(oos_sessions),
                               cost_model)
        oos_eq = oos_res.equity.loc[oos_sessions]
        report.windows.append({
            "train": (str(start.date()), str(train_end.date())),
            "test": (str(train_end.date()), str(test_end.date())),
            "is_annual_profit": _annual_log_profit(is_res.equity.loc[is_sessions]),
            "oos_annual_profit": _annual_log_profit(oos_eq),
        })
        oos_pieces.append(np.log(oos_eq / oos_eq.iloc[0]))
        start = start + pd.DateOffset(months=protocol.step_months)

    if report.windows:
        is_avg = float(np.mean([w["is_annual_profit"] for w in report.windows]))
        oos_avg = float(np.mean([w["oos_annual_profit"] for w in report.windows]))
        report.wfe = oos_avg / is_avg if abs(is_avg) > 1e-12 else 0.0
    if oos_pieces:
        chained, level = [], 0.0
        for piece in oos_pieces:
            chained.append(piece + level)
            level = float(chained[-1].iloc[-1])
        report.stitched_oos_equity = np.exp(pd.concat(chained))
    return report
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_walkforward.py -v`
Expected: PASS (1)

- [ ] **Step 5: Commit** — `git add src/number7/validation/walkforward.py tests/test_walkforward.py && git commit -m "feat(phase1): frozen-protocol walk-forward runner with WFE"`

---

### Task 11: Monkey test + Monte-Carlo bootstrap

**Files:**
- Create: `src/number7/validation/monkey.py`, `src/number7/validation/montecarlo.py`
- Test: `tests/test_monkey.py`, `tests/test_montecarlo.py`

**Interfaces:**
- `monkey_test(candidate_result, panel, rebalance_dates, cost_model, n_monkeys=1000, seed=0) -> dict` — builds `RandomTopN`-style monkeys **matched on the candidate's breadth** (median names held) and identical schedule/sizing/costs (Davey's matching, holding-period-preserving by construction — same weekly cadence, no IID shuffling); returns `{"profit_pctile": float, "dd_pctile": float, "beats_90": bool}` where `beats_90` requires net-profit percentile ≥ 0.9 **and** max-DD percentile ≥ 0.5 (candidate's DD no worse than the monkey median — profit must not come from outsized risk). (Blueprint Gate 4; n_monkeys=8000 in production config, 1000 default for CI speed.)
- `block_bootstrap_dd(daily_log_returns, block=10, n=2000, seed=0) -> dict` — stationary block bootstrap; returns `{"dd_p95": float, "dd_p99": float, "sharpe_ci90": (lo, hi)}` (autocorrelation-respecting bands — blueprint Gate 2/5 and the §8 brake calibration input).

- [ ] **Step 1: Write the failing tests** — `tests/test_monkey.py`

```python
import numpy as np
import pandas as pd

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import PanelView, StrategyManifest
from number7.validation.monkey import monkey_test


class BestDrift:
    """Cheats mildly on synthetic data: always holds the highest-drift name (known winner)."""
    manifest = StrategyManifest(name="best", family="t", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.close.columns)
        w["W"] = 1.0
        return w


def _panel_with_winner(n=504, seed=4):
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    cols = {f"S{i}": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))) for i in range(10)}
    cols["W"] = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.01, n)))   # drifting winner
    close = pd.DataFrame(cols, index=dates)
    ones = pd.DataFrame(True, index=dates, columns=close.columns)
    return PanelView(close=close, volume=close * 0 + 1e9, unadjusted_close=close, in_index=ones)


def test_winner_beats_monkeys_and_null_does_not():
    panel = _panel_with_winner()
    rb = weekly_rebalances(panel.close.index)
    cm = CostModel(min_half_spread_bps=0.0)
    winner = run_backtest(BestDrift(), panel, rb, cm)
    verdict = monkey_test(winner, panel, rb, cm, n_monkeys=200, seed=1)
    assert verdict["profit_pctile"] >= 0.9

    from number7.engine.strategy import RandomTopN
    null = run_backtest(RandomTopN(n=1, seed=99), panel, rb, cm)
    null_verdict = monkey_test(null, panel, rb, cm, n_monkeys=200, seed=1)
    assert null_verdict["profit_pctile"] < 0.9
```

— `tests/test_montecarlo.py`

```python
import numpy as np
import pytest

from number7.validation.montecarlo import block_bootstrap_dd


def test_bootstrap_bands_are_sane_and_deterministic():
    rng = np.random.default_rng(2)
    rets = rng.normal(0.0004, 0.01, 1000)
    a = block_bootstrap_dd(rets, block=10, n=500, seed=7)
    b = block_bootstrap_dd(rets, block=10, n=500, seed=7)
    assert a == b                                          # seeded determinism
    assert a["dd_p99"] <= a["dd_p95"] <= 0                 # drawdowns are negative
    lo, hi = a["sharpe_ci90"]
    assert lo < hi
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_monkey.py tests/test_montecarlo.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/validation/monkey.py`

```python
from __future__ import annotations

import numpy as np
import pandas as pd

from number7.engine.backtest import BacktestResult, run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, RandomTopN


def monkey_test(candidate: BacktestResult, panel: PanelView,
                rebalance_dates: pd.DatetimeIndex, cost_model: CostModel,
                n_monkeys: int = 1000, seed: int = 0) -> dict:
    held = (candidate.weights > 0).sum(axis=1)
    breadth = max(int(held.median()) if len(held) else 1, 1)
    cand = summary(candidate)
    profits, dds = [], []
    for k in range(n_monkeys):
        res = run_backtest(RandomTopN(n=breadth, seed=seed * 100_003 + k),
                           panel, rebalance_dates, cost_model)
        s = summary(res)
        profits.append(s["cagr"])
        dds.append(s["max_dd"])
    profit_pctile = float(np.mean([cand["cagr"] > p for p in profits]))
    dd_pctile = float(np.mean([cand["max_dd"] >= d for d in dds]))   # higher = shallower DD
    return {"profit_pctile": profit_pctile, "dd_pctile": dd_pctile,
            "beats_90": profit_pctile >= 0.9 and dd_pctile >= 0.5}
```

— `src/number7/validation/montecarlo.py`

```python
from __future__ import annotations

import numpy as np


def _max_dd(log_rets: np.ndarray) -> float:
    eq = np.exp(np.cumsum(log_rets))
    return float((eq / np.maximum.accumulate(eq) - 1.0).min())


def block_bootstrap_dd(daily_log_returns, block: int = 10, n: int = 2000,
                       seed: int = 0) -> dict:
    r = np.asarray(daily_log_returns, dtype=float)
    rng = np.random.default_rng(seed)
    L = len(r)
    dds, sharpes = [], []
    for _ in range(n):
        idx = []
        while len(idx) < L:
            s = int(rng.integers(0, L - block))
            idx.extend(range(s, s + block))
        path = r[np.array(idx[:L])]
        dds.append(_max_dd(path))
        sharpes.append(float(path.mean() / (path.std(ddof=0) or 1e-12) * np.sqrt(252)))
    dds, sharpes = np.array(dds), np.array(sharpes)
    return {"dd_p95": float(np.quantile(dds, 0.05)),
            "dd_p99": float(np.quantile(dds, 0.01)),
            "sharpe_ci90": (float(np.quantile(sharpes, 0.05)),
                            float(np.quantile(sharpes, 0.95)))}
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_monkey.py tests/test_montecarlo.py -v` → PASS (2)

- [ ] **Step 5: Commit** — `git add src/number7/validation/monkey.py src/number7/validation/montecarlo.py tests/test_monkey.py tests/test_montecarlo.py && git commit -m "feat(phase1): matched monkey test and block-bootstrap risk bands"`

---

### Task 12: Equal-weight benchmark + Gate-6 comparator

**Files:**
- Create: `src/number7/benchmarks/__init__.py`, `src/number7/benchmarks/ew.py`
- Test: `tests/test_benchmark.py`

**Interfaces:**
- Produces: `EqualWeightIndex` (a `Strategy`: equal-weights **all** in-index members at each rebalance — the blueprint Gate-6 benchmark, "defined in code"); `gate6(candidate_summary, benchmark_summary) -> dict` returning `{"sharpe_ratio_vs_bench": float, "suspicious": bool, "excess_cagr": float}` with `suspicious = candidate sharpe > 2 × benchmark sharpe` (Coqueret & Guida sniff test).

- [ ] **Step 1: Write the failing test** — `tests/test_benchmark.py`

```python
import pandas as pd

from number7.benchmarks.ew import EqualWeightIndex, gate6
from number7.engine.backtest import run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.live import build_panel


def test_ew_benchmark_holds_members_only(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.close.index[2]])
    res = run_backtest(EqualWeightIndex(), panel, rb, CostModel())
    w = res.weights.loc[rb[0]]
    assert w["AAPL"] > 0 and w["SPY"] == 0.0          # SPY not an index member
    assert abs(w.sum() - 1.0) < 1e-9


def test_gate6_flags_too_good():
    cand = {"sharpe": 2.5, "cagr": 0.4}
    bench = {"sharpe": 1.0, "cagr": 0.1}
    g = gate6(cand, bench)
    assert g["suspicious"] and g["excess_cagr"] == 0.3
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_benchmark.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/benchmarks/ew.py`

```python
from __future__ import annotations

import pandas as pd

from number7.engine.strategy import PanelView, StrategyManifest


class EqualWeightIndex:
    """Gate-6 benchmark: equal-weight every current index member, weekly, same costs."""

    def __init__(self, exclude: tuple[str, ...] = ("SPY",)) -> None:
        self.manifest = StrategyManifest(name="ew_index", family="benchmark",
                                         origin="human", params={"exclude": list(exclude)})
        self._exclude = set(exclude)

    def target_weights(self, view: PanelView) -> pd.Series:
        members = view.in_index.iloc[-1]
        picks = [s for s in members.index[members] if s not in self._exclude]
        w = pd.Series(0.0, index=view.close.columns)
        if picks:
            w[picks] = 1.0 / len(picks)
        return w


def gate6(candidate_summary: dict, benchmark_summary: dict) -> dict:
    bs = benchmark_summary.get("sharpe", 0.0)
    ratio = candidate_summary["sharpe"] / bs if bs > 0 else float("inf")
    return {"sharpe_ratio_vs_bench": ratio,
            "suspicious": ratio > 2.0,
            "excess_cagr": candidate_summary["cagr"] - benchmark_summary["cagr"]}
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_benchmark.py -v` → PASS (2)

- [ ] **Step 5: Commit** — `git add src/number7/benchmarks tests/test_benchmark.py && git commit -m "feat(phase1): equal-weight benchmark and gate-6 sniff test"`

---

### Task 13: Lot book + wash-sale handling

**Files:**
- Create: `src/number7/execution/__init__.py`, `src/number7/execution/lots.py`
- Test: `tests/test_lots.py`

**Interfaces:**
- Produces: `Lot` (dataclass: `symbol, open_date, qty, basis`); `LotBook` with `buy(symbol, date, qty, price)`, `sell(symbol, date, qty, price) -> list[RealizedLot]` (FIFO; `RealizedLot`: `symbol, open_date, close_date, qty, proceeds, basis, pnl`), `wash_sales(window_days=30) -> list[dict]` (realized losses where the same symbol was re-bought within ±window — each: `symbol, loss_date, repurchase_date, disallowed_loss`), `blackout_until(symbol) -> date | None` (loss date + 30 days when a loss was realized — feeds `reentry_blackout_days` enforcement in Phase 2; blueprint §8 tax clause).

- [ ] **Step 1: Write the failing test** — `tests/test_lots.py`

```python
from datetime import date

import pytest

from number7.execution.lots import LotBook


def test_fifo_realization():
    book = LotBook()
    book.buy("AAPL", date(2026, 1, 5), 10, 100.0)
    book.buy("AAPL", date(2026, 2, 2), 10, 110.0)
    realized = book.sell("AAPL", date(2026, 3, 2), 15, 120.0)
    assert sum(r.qty for r in realized) == 15
    assert realized[0].basis == pytest.approx(1000.0)      # first lot fully consumed
    assert realized[1].qty == 5 and realized[1].basis == pytest.approx(550.0)
    assert sum(r.pnl for r in realized) == pytest.approx(15 * 120 - 1000 - 550)


def test_wash_sale_detected_on_reentry_within_30d():
    book = LotBook()
    book.buy("XYZ", date(2026, 1, 5), 10, 100.0)
    book.sell("XYZ", date(2026, 2, 2), 10, 90.0)           # realized loss
    book.buy("XYZ", date(2026, 2, 20), 10, 92.0)           # re-entry 18 days later
    ws = book.wash_sales()
    assert len(ws) == 1
    assert ws[0]["symbol"] == "XYZ"
    assert ws[0]["disallowed_loss"] == pytest.approx(100.0)
    assert book.blackout_until("XYZ") == date(2026, 3, 4)  # loss date + 30d


def test_no_wash_sale_outside_window():
    book = LotBook()
    book.buy("XYZ", date(2026, 1, 5), 10, 100.0)
    book.sell("XYZ", date(2026, 2, 2), 10, 90.0)
    book.buy("XYZ", date(2026, 3, 20), 10, 92.0)           # 46 days later
    assert book.wash_sales() == []
```

- [ ] **Step 2: Run to verify failure** — `uv run pytest tests/test_lots.py -v` → FAIL

- [ ] **Step 3: Implement** — `src/number7/execution/lots.py`

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Lot:
    symbol: str
    open_date: date
    qty: float
    basis: float          # total dollars paid for the remaining qty


@dataclass
class RealizedLot:
    symbol: str
    open_date: date
    close_date: date
    qty: float
    proceeds: float
    basis: float

    @property
    def pnl(self) -> float:
        return self.proceeds - self.basis


@dataclass
class LotBook:
    open_lots: dict[str, list[Lot]] = field(default_factory=dict)
    realized: list[RealizedLot] = field(default_factory=list)
    buys: list[tuple[str, date]] = field(default_factory=list)

    def buy(self, symbol: str, d: date, qty: float, price: float) -> None:
        self.open_lots.setdefault(symbol, []).append(Lot(symbol, d, qty, qty * price))
        self.buys.append((symbol, d))

    def sell(self, symbol: str, d: date, qty: float, price: float) -> list[RealizedLot]:
        out: list[RealizedLot] = []
        remaining = qty
        lots = self.open_lots.get(symbol, [])
        while remaining > 1e-12 and lots:
            lot = lots[0]
            take = min(lot.qty, remaining)
            basis_part = lot.basis * (take / lot.qty)
            out.append(RealizedLot(symbol, lot.open_date, d, take, take * price, basis_part))
            lot.qty -= take
            lot.basis -= basis_part
            remaining -= take
            if lot.qty <= 1e-12:
                lots.pop(0)
        if remaining > 1e-12:
            raise ValueError(f"sell exceeds open quantity for {symbol}")
        self.realized.extend(out)
        return out

    def wash_sales(self, window_days: int = 30) -> list[dict]:
        out = []
        for r in self.realized:
            if r.pnl >= 0:
                continue
            for sym, bd in self.buys:
                if sym == r.symbol and bd != r.open_date \
                        and abs((bd - r.close_date).days) <= window_days and bd > r.open_date:
                    out.append({"symbol": r.symbol, "loss_date": r.close_date,
                                "repurchase_date": bd, "disallowed_loss": -r.pnl})
                    break
        return out

    def blackout_until(self, symbol: str) -> date | None:
        losses = [r.close_date for r in self.realized if r.symbol == symbol and r.pnl < 0]
        return (max(losses) + timedelta(days=30)) if losses else None
```

- [ ] **Step 4: Run to verify pass** — `uv run pytest tests/test_lots.py -v` → PASS (3)

- [ ] **Step 5: Commit** — `git add src/number7/execution tests/test_lots.py && git commit -m "feat(phase1): FIFO lot book with wash-sale detection and blackout"`

---

### Task 14: Alpaca paper MOC probe

**Files:**
- Create: `src/number7/brokers/__init__.py`, `src/number7/brokers/alpaca_probe.py`
- Test: `tests/test_alpaca_probe.py` (marked `paper`)

**Interfaces:**
- Produces: `run_probe(symbol="SPY", qty=1) -> dict` — submits a paper **MOC** order (`time_in_force="cls"`) before the cutoff, polls until filled, returns `{"accepted": bool, "filled": bool, "fill_price": float, "fill_time": str, "order_id": str}`. Manual gate (blueprint Phase 1): run on a trading day before ~15:45 ET, then next morning compare `fill_price` to the official close in the snapshot (within a few cents on SPY). Settings additions: `alpaca_key_id: str | None`, `alpaca_secret: str | None` (add to `Settings`, env `N7_ALPACA_KEY_ID` / `N7_ALPACA_SECRET`; **paper keys only** in Phase 1).

- [ ] **Step 1: Add dependency + settings fields**

```bash
uv add alpaca-py
```

Append to `Settings` in `src/number7/config.py`:

```python
    alpaca_key_id: str | None = None
    alpaca_secret: str | None = None
```

- [ ] **Step 2: Implement** — `src/number7/brokers/alpaca_probe.py`

```python
from __future__ import annotations

import json
import time

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from number7.config import get_settings


def run_probe(symbol: str = "SPY", qty: int = 1) -> dict:
    s = get_settings()
    client = TradingClient(s.alpaca_key_id, s.alpaca_secret, paper=True)
    order = client.submit_order(MarketOrderRequest(
        symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.CLS))
    accepted = order.status is not None
    fill_price, fill_time, filled = None, None, False
    for _ in range(120):                       # poll up to ~10 min after the close
        o = client.get_order_by_id(order.id)
        if o.filled_at is not None:
            filled = True
            fill_price = float(o.filled_avg_price)
            fill_time = str(o.filled_at)
            break
        time.sleep(5)
    return {"accepted": accepted, "filled": filled, "fill_price": fill_price,
            "fill_time": fill_time, "order_id": str(order.id)}


if __name__ == "__main__":
    print(json.dumps(run_probe(), indent=2))
```

- [ ] **Step 3: Paper-marked test** — `tests/test_alpaca_probe.py`

```python
import pytest

from number7.brokers.alpaca_probe import run_probe

pytestmark = pytest.mark.paper


def test_moc_order_accepted_and_filled_at_close():
    r = run_probe("SPY", 1)
    assert r["accepted"], r
    assert r["filled"], "MOC not filled on paper - Phase 2 paper parity is INVALID (blueprint §14)"
```

- [ ] **Step 4: Manual acceptance run** (a trading day, before 15:45 ET; paper keys in `.env`)

Run: `uv run pytest -m paper -v` (or `uv run python -m number7.brokers.alpaca_probe`)
Expected: PASS; next morning verify `fill_price` ≈ that day's official SPY close from the nightly snapshot (`select close from prices where symbol='SPY' order by date desc limit 1`). Document the observed deviation in `docs/` — it seeds the empirical slippage bands (§9).

- [ ] **Step 5: Commit** — `git add src/number7/brokers tests/test_alpaca_probe.py pyproject.toml uv.lock src/number7/config.py && git commit -m "feat(phase1): alpaca paper MOC probe"`

---

## Phase 1 acceptance (blueprint §10 + §14 amendments)

- [ ] `uv run pytest` — full offline suite green (all 14 tasks).
- [ ] Known-answer tests pass: null strategy ≈ zero (Task 7); `LookaheadTrap` caught by causality harness (Task 6); `expected_max_sr(1000, 1) ≈ 3.26` (Task 8).
- [ ] Golden-replay parity green (Task 5) — the Phase-2 order service contract is pinned.
- [ ] Ledger rejects a scrapped param-space re-registration (Task 9) — tweak-and-retest guard live.
- [ ] Paper MOC probe verified against the official close (Task 14).
- [ ] Every backtest invocation in later work goes through a wrapper that calls `Ledger.log_run` — enforced by convention now, by the Phase-3 orchestrator later.

## Self-review (done at authoring)

1. **Spec coverage vs blueprint Phase 1:** Tier-1 engine ✔ (T4, causal by construction), cost model ✔ (T3), walk-forward frozen protocol + WFE ✔ (T10), PSR/DSR + tiers ✔ (T8), trials ledger + dedup/lineage + scrap guard ✔ (T9), monkey matched ✔ (T11), MC bands ✔ (T11), golden-replay ✔ (T5), truncate-and-compare CI ✔ (T6), known-answer calibration ✔ (T7), Alpaca MOC probe ✔ (T14), wash-sale/lot decision ✔ (T13), EW benchmark in code ✔ (T12). Newey-West-style effective-sample correction is covered by the block-bootstrap Sharpe CI (T11) — the gate consumes the CI, not a raw t-stat.
2. **Placeholder scan:** Task 10 Step 3 contained drafting scaffolding — explicitly flagged and replaced by Step 4's final block; no other placeholders.
3. **Type consistency:** `PanelView`/`StrategyManifest` (T2) used identically in T4–T12; `summary()` keys consumed by `monkey_test`/`gate6` match T4's dict; `compute_live_targets` signature identical in T5 and T6; `Settings` extension in T14 matches Phase-0 Task 1 model.
