# Clenow Momentum Sleeve Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Phase-2 baseline sleeve — Clenow equity momentum on a dual-basis snapshot — as a stateless strategy plus a shared holdings-aware resolver, run it through the full validation gauntlet (fixing the three gauntlet defects it exposes), and produce the calibration memo.

**Architecture:** The snapshot gains a second, capital-adjusted price basis (`px_*`) alongside total-return (`tr_*`), because a price basis cannot be derived from what we store. `PanelView` carries both, with `close` **renamed** so every call site must choose a basis. `ClenowMomentum.target_weights(view) -> Slate` stays a pure function of the panel (keeping the truncate-and-compare causality proof total); a separate `sizing.resolve_book(slate, current, config)` does admission, budgeted fill, caps, floor, normalization and the drift band, and is called identically by `run_backtest` and `compute_live_targets`.

**Tech Stack:** Python ≥3.13, pandas 3, numpy, duckdb, pydantic v2 + pydantic-settings, exchange-calendars, pytest, ruff. Builds on Phase 0 (`Settings`, snapshot layout, `load_price_panel`, `in_index_flags`) and Phase 1 (`run_backtest`, `compute_live_targets`, `causality_violations`, `walk_forward`, `monkey_test`, `Ledger`, `PreRegistration`, `dsr_hurdle`).

## Global Constraints

Copied verbatim from `docs/superpowers/specs/2026-07-23-clenow-momentum-sleeve-design.md`. Every task's requirements implicitly include this section.

- **Timing contract (blueprint §4.1, normative):** weights executed at close of rebalance date `T` are computed from data **≤ close of T−1**. This now also covers the *sizing* inputs: `sleeve_equity` and `current` holdings both come from T−1, never from T.
- **Basis assignment (spec §2), normative:**
  - momentum regression, SMA100, regime SMA200, gap filter, ATR20, `close/ATR` ratio → **capital-adjusted (`px_*`)**
  - portfolio P&L, equity curve, benchmark comparison → **total-return (`tr_close`)**
  - MOC fill price, share rounding, ADV, broker reconciliation → **raw (`raw_close`)**
  - Each computation must be internally consistent within its basis. Mixing an adjusted close with raw high/low inside a true range is a bug.
- **`ann_factor = 250`** — pinned constant, excluded from the searched parameter space (OQ-2).
- **Not parameters** (pinned, excluded from the declared space): `ann_factor`, Wilder-vs-simple ATR smoothing, drift-band relative-vs-absolute.
- **Searched parameters only:** `lookback, atr_window, ma_filter, regime_ma, gap_threshold, risk_factor, hold_top_pct, max_positions, drift_band`.
- **`reentry_blackout_days = 0`** — recorded decision, Clenow-faithful.
- **Strategy contract:** `target_weights(view) -> Slate`, **stateless**, signature unchanged (view only). Do not reintroduce holdings into the strategy. `Slate.weights` are **absolute** ATR-parity weights for all eligible names (unbudgeted) — never normalized to sum 1.
- **DSR hurdle 0.98** (low-N and/or LLM origin), never 0.95. Reference replication and searched variant are **separate pre-registrations**.
- **Ledger accounting:** ablations, the profile pair, and cost-sensitivity runs are **diagnostics, excluded from the DSR trial count**. Any parameter change made in response to calibration results spawns a **new** pre-registration and counts as a new trial.
- **Two frozen profiles**, not a runtime toggle: *Reference Clenow* (source rules, overlays off — fidelity evidence only, never deployable evidence) and *Deployable sleeve* (all §8 caps, costs). `caps_enabled` as a single flag is retired.
- **Snapshots are immutable and versioned.** The dual-basis change produces a **new** snapshot id, never an edit of an existing one.
- **Determinism:** every stochastic component takes an explicit seed. New RNG use must be a pure function of `(seed, date)` — do not repeat `RandomTopN`'s call-count-dependent bug (spec §15).
- **Tests never touch the network** except the `vm` and `paper` marks, which are deselected by default.
- Chain test commands with `set -o pipefail` when piping to `tail`/`grep` — a bare pipe swallows pytest's exit code.
- `ruff check src tests` must be clean; `line-length = 100`.
- Sub-1.0 gross is expected behaviour (regime-off, ATR parity not consuming equity) and is not a bug.
- A gauntlet **failure is an acceptable outcome** and is documented as a kill. This is a fidelity exercise, not a search for a passing grade.

## Interpretation decisions made while writing this plan

The spec pins most things. These five were under-determined; each is pinned here with its rationale so the implementer does not re-decide, and so Viktor can veto before Task 1.

1. **Budgeted fill terminates at the marginal name.** §8.2 says "until equity is exhausted … the marginal name is skipped, not partially filled". It does not say whether the walk continues to lower-ranked names that would fit. Pinned: **terminate**. Continuing would promote a lower-ranked name over the marginal one, breaking strict rank priority.
2. **Floor is a single pass, shortfall to cash.** §8.2 step 5 offers "iterate to a fixed point or leave the shortfall in cash". Since we never re-normalize upward after dropping, one pass *is* the fixed point. Pinned: single pass.
3. **`PanelView` gains `assetid`.** §7's table lists only price frames, but §6.1 requires ties to break on "a stable security identifier — never ticker order". Symbols are not stable across time; Norgate's `assetid` is. Pinned: `PanelView.assetid: pd.Series` (symbol → assetid), sourced from `metadata.parquet`. Rank key is `(-score, assetid)` with missing assetid sorted last, and mergesort stability as the final total-order fallback.
4. **ATR burn-in = `atr_window * 5` bars.** §6.3's "21+ valid bars" is a floor, but §6.5 demands a pinned seed *and* burn-in so the §12 known-answer test has a unique answer. Pinned: ATR is computed on the trailing `atr_window * 5` true ranges after the seed window, and eligibility requires `atr_window * 5 + 1` valid bars. This is stricter than §6.3 and is already implied by `ma_filter = 100`.
5. **Cash rate: primary runs at 0.0, with mandatory 2%/4% diagnostics.** §11.3 says pin it and state it in the memo. We have no bill series in the snapshot, so inventing a historical rate path would be fabrication. Pinned: engine gains an explicit `cash_annual_rate`, primary runs use `0.0` (conservative and stated), and the memo must carry the 2% and 4% diagnostic pair quantifying the handicap.

Two consequences worth stating because they look like bugs and are not:

- **The fill runs on uncapped weights, so the cap can strand budget.** §8.2 orders fill (2) before cap (3). A name with an ATR-parity weight of 0.40 consumes 0.40 of the budget and is then clipped to 0.10, leaving 0.30 unused. That is what the spec says; do not "optimize" the ordering.
- **Turnover is measured against `state_at_signal`, not the drifted book.** Orders are sized from T−1 information, which is what the live path does; the engine's existing "exact closing-weight attainment" assumption (§9) absorbs the intra-day drift. A drift-band retention therefore produces exactly zero turnover, which is the whole point of the band.

## File Structure

```
src/number7/
├── config.py                      # Task 10 — trading_mode + risk_layer_version gate
├── data/
│   ├── store.py                   # Task 1 — PRICE_COLS gains px_*/tr_*/raw_close
│   ├── sync.py                    # Task 1 — dual-adjustment pull + merge
│   ├── snapshot.py                # Task 1 — SnapshotMeta.bases
│   └── qc.py                      # Task 1 — per-basis OHLC sanity, bases checks
├── engine/
│   ├── strategy.py                # Task 2/3 — PanelView dual basis; Slate; protocol
│   ├── backtest.py                # Task 5 — state_at_signal, stale, cash, resolver
│   └── live.py                    # Task 2/5 — build_panel; compute_live_targets(current, sizing)
├── strategies/                    # NEW package
│   ├── __init__.py
│   ├── sizing.py                  # Task 4 — SizingConfig, resolve_book, apply_drift_band
│   └── clenow.py                  # Task 8 — ClenowMomentum + math helpers
├── benchmarks/ew.py               # Task 3 — returns a Slate
├── validation/
│   ├── causality.py               # Task 7 — closed_loop_violations
│   ├── walkforward.py             # Task 6 — carry IS end-state into OOS
│   └── monkey.py                  # Task 9 — injectable matched null
└── research/
    ├── preregs.py                 # Task 11 — the two PreRegistrations
    └── calibrate_clenow.py        # Task 12 — runner + memo writer
tests/
├── conftest.py                    # Tasks 1/2 — dual-basis fixture + make_panel helper
├── test_sizing.py                 # Task 4
├── test_clenow.py                 # Task 8
└── (existing test files updated in Tasks 1-3, 5-7, 9-10)
docs/research/2026-08-clenow-calibration-memo.md   # Task 12
```

---

### Task 1: Dual-basis snapshot (sync, schema, QC, metadata)

Phase-0 data work, forced by OQ-1. Must land and promote green **before** any strategy code.
The `norgate-service` bridge already supports `adjustment="capital"` — no VM-side change.

**Files:**
- Modify: `src/number7/data/store.py:10` (`PRICE_COLS`), `src/number7/data/store.py:26-27` (`close_matrix`)
- Modify: `src/number7/data/sync.py:27-47` (`_pull_prices`), `src/number7/data/sync.py:84-91` (meta)
- Modify: `src/number7/data/snapshot.py:13-21` (`SnapshotMeta`)
- Modify: `src/number7/data/qc.py:38-53` (schema + OHLC), `src/number7/data/qc.py:72` (outlier pivot)
- Test: `tests/conftest.py`, `tests/test_sync.py`, `tests/test_qc.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PRICE_COLS = ["symbol", "date", "px_open", "px_high", "px_low", "px_close", "tr_open", "tr_high", "tr_low", "tr_close", "raw_close", "volume"]`; `SnapshotMeta.bases: list[str]` (required, no default); `close_matrix(panel, col="tr_close")`.

- [ ] **Step 1: Write the failing sync test**

Replace the `adjustment` assertion in `tests/test_sync.py::FakeClient` and add the new cases.

```python
class FakeClient:
    def watchlist_symbols(self, name):
        assert name == "S&P 500 Current & Past"
        return ["AAPL", "ATVI"]

    def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
        assert adjustment in ("totalreturn", "capital")
        days = SESSIONS if symbol != "ATVI" else SESSIONS[:2]
        scale = 1.0 if adjustment == "capital" else 1.05      # TR drifts above price
        return pd.DataFrame({"date": days, "open": 1.0 * scale, "high": 1.1 * scale,
                             "low": 0.9 * scale, "close": 1.0 * scale,
                             "volume": 100, "unadjusted_close": 0.98})
    # sp500_membership_intervals / metadata_batch unchanged


def test_run_sync_stores_both_bases(tmp_path):
    root = run_sync(_settings(tmp_path), client=FakeClient(), health=_health())
    prices = pd.read_parquet(SnapshotPaths(root).prices)
    assert list(prices.columns) == ["symbol", "date", "px_open", "px_high", "px_low",
                                    "px_close", "tr_open", "tr_high", "tr_low",
                                    "tr_close", "raw_close", "volume"]
    row = prices.iloc[0]
    assert row["px_close"] == pytest.approx(1.0)
    assert row["tr_close"] == pytest.approx(1.05)
    assert row["raw_close"] == pytest.approx(0.98)
    assert read_meta(SnapshotPaths(root)).bases == ["totalreturn", "capital"]


def test_raw_close_disagreement_between_bases_is_fatal(tmp_path):
    class SkewedClient(FakeClient):
        def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
            df = super().price_timeseries(symbol, start, end, adjustment)
            if adjustment == "capital":
                df["unadjusted_close"] = 0.97      # raw price must be basis-independent
            return df

    with pytest.raises(RuntimeError, match="raw close differs"):
        run_sync(_settings(tmp_path), client=SkewedClient(), health=_health())


def test_session_grid_disagreement_between_bases_is_fatal(tmp_path):
    class ShortCapClient(FakeClient):
        def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
            df = super().price_timeseries(symbol, start, end, adjustment)
            return df.iloc[:-1] if adjustment == "capital" else df

    with pytest.raises(RuntimeError, match="session grids disagree"):
        run_sync(_settings(tmp_path), client=ShortCapClient(), health=_health())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set -o pipefail && uv run pytest tests/test_sync.py -v`
Expected: FAIL — column list mismatch, `SnapshotMeta` has no `bases`, no `RuntimeError` raised.

- [ ] **Step 3: Widen the store schema**

`src/number7/data/store.py` — replace `PRICE_COLS` and make `close_matrix` name its basis.

```python
PRICE_COLS = ["symbol", "date",
              "px_open", "px_high", "px_low", "px_close",      # capital-adjusted: signals
              "tr_open", "tr_high", "tr_low", "tr_close",      # total-return: P&L
              "raw_close", "volume"]                           # raw: fills, ADV, reconciliation

BASES = {"totalreturn": "tr", "capital": "px"}   # adjustment -> stored column prefix


def close_matrix(panel: pd.DataFrame, col: str = "tr_close") -> pd.DataFrame:
    return panel.pivot(index="date", columns="symbol", values=col).sort_index()
```

- [ ] **Step 4: Record the bases in snapshot metadata**

`src/number7/data/snapshot.py` — add to `SnapshotMeta`, **without a default**, so an
old-schema `meta.json` fails validation loudly instead of silently claiming a price basis.

```python
class SnapshotMeta(BaseModel):
    db_date: date
    created_at: datetime
    history_start: date
    watchlist: str
    n_symbols: int
    n_price_rows: int
    bases: list[str]             # adjustments present, e.g. ["totalreturn", "capital"].
    # REQUIRED (no default) on purpose: a pre-dual-basis snapshot must be detectably
    # unusable for the momentum sleeve, never silently mis-ranked (spec §2).
    n_empty_symbols: int = 0
    file_sha256: dict[str, str]
```

- [ ] **Step 5: Pull both adjustments and merge them in sync**

`src/number7/data/sync.py` — replace `_pull_prices` and add the two helpers above it.
The nightly pull now makes two REST calls per symbol; runtime roughly doubles (~500 symbols
× 2). That is expected and acceptable for a 22:30 ET job.

```python
import numpy as np

from number7.data.store import BASES, PRICE_COLS

_OHLC = ("open", "high", "low", "close")


def _pull_basis(client, sym: str, start: str, adjustment: str) -> pd.DataFrame | None:
    df = client.price_timeseries(sym, start=start, adjustment=adjustment)
    if df.empty:
        return None
    prefix = BASES[adjustment]
    out = df[["date", *_OHLC, "unadjusted_close", "volume"]].copy()
    return out.rename(columns={c: f"{prefix}_{c}" for c in _OHLC})


def _pull_symbol(client, sym: str, start: str) -> pd.DataFrame | None:
    """Both bases for one symbol, merged on the session grid. A symbol that is empty in
    ONE basis but not the other is a bridge fault, not a pre-history delisting."""
    frames = {a: _pull_basis(client, sym, start, a) for a in BASES}
    present = [a for a, d in frames.items() if d is not None]
    if not present:
        return None
    if len(present) != len(BASES):
        raise RuntimeError(f"{sym}: bases {present} returned data but "
                           f"{sorted(set(BASES) - set(present))} did not")
    tr, px = frames["totalreturn"], frames["capital"]
    m = tr.merge(px.drop(columns=["volume"]), on="date", how="inner",
                 suffixes=("", "_px"))
    if not (len(m) == len(tr) == len(px)):
        raise RuntimeError(f"{sym}: totalreturn/capital session grids disagree "
                           f"({len(tr)} vs {len(px)} bars, {len(m)} common)")
    if not np.allclose(m["unadjusted_close"], m["unadjusted_close_px"],
                       rtol=1e-9, atol=1e-12):
        raise RuntimeError(f"{sym}: raw close differs between adjustment bases - "
                           "the bridge is not honouring the adjustment parameter")
    m = m.rename(columns={"unadjusted_close": "raw_close"}) \
         .drop(columns=["unadjusted_close_px"])
    m["symbol"] = sym
    return m[PRICE_COLS]


def _pull_prices(client, symbols: list[str], start: str,
                 required: set[str] = frozenset()) -> tuple[pd.DataFrame, list[str]]:
    """Pull per-symbol history in BOTH bases. A symbol may legitimately return no bars in
    range (delisted before `start` — the Current & Past watchlist reaches decades back),
    so empties are tolerated and reported — EXCEPT `required` symbols (e.g. SPY),
    whose absence is a hard failure."""
    frames, empty = [], []
    for sym in symbols:
        df = _pull_symbol(client, sym, start)
        if df is None:
            if sym in required:
                raise RuntimeError(f"bridge returned no data for required symbol {sym}")
            empty.append(sym)
            continue
        frames.append(df)
    if not frames:
        raise RuntimeError(f"bridge returned no price data for any of {len(symbols)} symbols "
                           "(outage, auth failure, or misconfigured watchlist?)")
    return pd.concat(frames, ignore_index=True), empty
```

In `run_sync`, add `bases=list(BASES)` to the `SnapshotMeta(...)` call:

```python
    write_meta(paths, SnapshotMeta(
        db_date=health.db_date, created_at=datetime.now(timezone.utc),
        history_start=settings.history_start, watchlist=settings.watchlist,
        n_symbols=len(symbols), n_price_rows=len(prices),
        n_empty_symbols=len(empty_symbols), bases=list(BASES),
        file_sha256={p.name: _sha256(p) for p in (paths.prices, paths.membership,
                                                  paths.metadata)},
    ))
```

- [ ] **Step 6: Run the sync tests to verify they pass**

Run: `set -o pipefail && uv run pytest tests/test_sync.py -v`
Expected: PASS (all six tests).

- [ ] **Step 7: Update the shared snapshot fixture**

`tests/conftest.py` — emit the new columns and the `bases` field. Keep the two bases
numerically distinct so the QC distinctness check has something to see.

```python
def _bars(symbol: str, days: list[date], px: float) -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": symbol,
        "date": pd.to_datetime(days),
        "px_open": px, "px_high": px * 1.01, "px_low": px * 0.99, "px_close": px,
        "tr_open": px * 1.02, "tr_high": px * 1.03, "tr_low": px * 1.01,
        "tr_close": px * 1.02,
        "raw_close": px * 0.98, "volume": 1_000_000,
    })
```

and in the `fake_snapshot` fixture:

```python
    meta = SnapshotMeta(db_date=date(2026, 7, 2), created_at=datetime.now(timezone.utc),
                        history_start=date(2004, 1, 1), watchlist="S&P 500 Current & Past",
                        n_symbols=3, n_price_rows=len(prices),
                        bases=["totalreturn", "capital"], file_sha256={})
```

- [ ] **Step 8: Write the failing QC tests**

Add to `tests/test_qc.py`, and update the two existing tests that write price columns.

```python
def test_ohlc_violation_fails(fake_snapshot):            # UPDATED: px basis
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "px_low"] = df.loc[0, "px_high"] + 1
    df.to_parquet(p.prices, index=False)
    issues = run_qc(fake_snapshot)
    assert not qc_passes(issues)
    assert any(i.check == "ohlc_sanity" and "px" in i.detail for i in issues)


def test_tr_basis_is_also_ohlc_checked(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "tr_high"] = df.loc[0, "tr_low"] - 1
    df.to_parquet(p.prices, index=False)
    assert any(i.check == "ohlc_sanity" and "tr" in i.detail
               for i in run_qc(fake_snapshot))


def test_nan_ohlc_fails_qc(fake_snapshot):               # UPDATED: px basis
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "px_close"] = float("nan")
    df.to_parquet(p.prices, index=False)
    assert any(i.check == "ohlc_sanity" for i in run_qc(fake_snapshot))


def test_missing_basis_in_meta_fails(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    meta = read_meta(p)
    meta.bases = ["totalreturn"]
    p.meta.write_text(meta.model_dump_json(indent=2))
    assert any(i.check == "bases_recorded" for i in run_qc(fake_snapshot))


def test_identical_bases_over_a_long_span_fails(fake_snapshot):
    """A bridge that ignores `adjustment` returns the same series twice; over a
    multi-year S&P pull the two bases cannot be identical everywhere."""
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    long_days = pd.bdate_range("2020-01-01", "2022-01-01")
    dup = pd.DataFrame({"symbol": "DUP", "date": long_days,
                        "px_open": 10.0, "px_high": 10.1, "px_low": 9.9, "px_close": 10.0,
                        "tr_open": 10.0, "tr_high": 10.1, "tr_low": 9.9, "tr_close": 10.0,
                        "raw_close": 10.0, "volume": 1_000_000})
    pd.concat([df, dup], ignore_index=True).to_parquet(p.prices, index=False)
    assert any(i.check == "bases_distinct" for i in run_qc(fake_snapshot))
```

Also update `test_history_older_than_calendar_default_bound`'s `old` DataFrame to the new
column set (same 11 columns as `dup` above, symbol `OLDCO`, the six `jan04` dates).

- [ ] **Step 9: Run the QC tests to verify they fail**

Run: `set -o pipefail && uv run pytest tests/test_qc.py -v`
Expected: FAIL — `ohlc_sanity` reads `open/high/low/close` which no longer exist (KeyError),
and neither `bases_recorded` nor `bases_distinct` exists.

- [ ] **Step 10: Extend QC to both bases**

`src/number7/data/qc.py` — replace check 2, add checks 9 and 10, and point the outlier
pivot at the P&L basis.

```python
    # 2. ohlc sanity, PER BASIS (NaN comparisons are False, so missing prices must be
    # caught explicitly). Each basis is internally consistent or the snapshot is bad.
    for prefix in ("px", "tr"):
        o, h, low, c = (f"{prefix}_{x}" for x in ("open", "high", "low", "close"))
        ohlc = prices[[o, h, low, c]]
        bad = prices[(prices[low] > prices[[o, c]].min(axis=1))
                     | (prices[h] < prices[[o, c]].max(axis=1))
                     | (prices[low] > prices[h])
                     | (ohlc <= 0).any(axis=1)
                     | ohlc.isna().any(axis=1)]
        if len(bad):
            issues.append(_err("ohlc_sanity", f"{prefix}: {len(bad)} bad bars, first: "
                               f"{bad.iloc[0]['symbol']} {bad.iloc[0]['date'].date()}"))
    if (prices["raw_close"] <= 0).any() or prices["raw_close"].isna().any():
        issues.append(_err("ohlc_sanity", "raw_close: non-positive or missing values"))
```

```python
    # 4. outlier returns without an index move (P&L basis)
    close = prices.pivot(index="date", columns="symbol", values="tr_close").sort_index()
```

```python
    # 9. metadata records the bases actually stored
    meta = read_meta(paths)
    missing = {"totalreturn", "capital"} - set(meta.bases)
    if missing:
        issues.append(_err("bases_recorded", f"meta.bases={meta.bases} missing {sorted(missing)}"))

    # 10. the two bases must actually differ somewhere. A bridge that silently ignores
    # `adjustment` returns the same series twice; over a multi-year pull of hundreds of
    # dividend payers, px_close == tr_close everywhere is impossible.
    span_years = (prices["date"].max() - prices["date"].min()).days / 365.25
    if span_years >= 1 and bool((prices["px_close"] == prices["tr_close"]).all()):
        issues.append(_err("bases_distinct", "px_close == tr_close on every row over "
                           f"{span_years:.1f}y - the capital basis is not distinct"))
```

Reuse the existing `span_years` computation for check 8 rather than computing it twice —
hoist the single assignment above check 8 and drop the duplicate.

- [ ] **Step 11: Run the full offline suite**

Run: `set -o pipefail && uv run pytest 2>&1 | tail -20`
Expected: `tests/test_store.py`, `tests/test_benchmark.py`, `tests/test_causality.py`,
`tests/test_live_parity.py` fail (they read `close`/`unadjusted_close` off the panel) — that
is Task 2's work. `test_sync.py`, `test_qc.py`, `test_snapshot.py`, `test_nightly.py` PASS.

- [ ] **Step 12: Fix `tests/test_store.py`**

```python
def test_load_price_panel_filters(fake_snapshot):
    panel = load_price_panel(fake_snapshot, symbols=["AAPL"], start="2026-06-30")
    assert set(panel["symbol"]) == {"AAPL"}
    assert panel["date"].min() == pd.Timestamp("2026-06-30")
    assert list(panel.columns) == ["symbol", "date", "px_open", "px_high", "px_low",
                                   "px_close", "tr_open", "tr_high", "tr_low",
                                   "tr_close", "raw_close", "volume"]


def test_close_matrix_defaults_to_total_return(fake_snapshot):
    tidy = load_price_panel(fake_snapshot)
    tr = close_matrix(tidy)
    px = close_matrix(tidy, col="px_close")
    assert list(tr.columns) == ["AAPL", "ATVI", "SPY"]
    assert tr.index.is_monotonic_increasing
    assert pd.isna(tr.loc["2026-07-01", "ATVI"])
    assert tr.loc["2026-06-29", "AAPL"] > px.loc["2026-06-29", "AAPL"]
```

Run: `set -o pipefail && uv run pytest tests/test_store.py tests/test_sync.py tests/test_qc.py -v`
Expected: PASS.

- [ ] **Step 13: Commit**

```bash
git add src/number7/data tests/conftest.py tests/test_sync.py tests/test_qc.py tests/test_store.py
git commit -m "feat(data): pull and store a capital-adjusted price basis alongside total-return

Clenow ranks price (spec OQ-1), and a price basis cannot be derived from the stored
total-return series - unadjusted_close is split-unadjusted. Sync now pulls both
adjustments per symbol and merges them on the session grid; the store schema names
each basis explicitly (px_*/tr_*/raw_close) so a reader cannot mix them by accident.

SnapshotMeta.bases is required with no default: a pre-dual-basis snapshot must be
detectably unusable for the momentum sleeve, not silently mis-ranked.

QC now runs OHLC sanity per basis and adds two checks - bases_recorded, and
bases_distinct, which catches a bridge that silently ignores the adjustment parameter."
```

- [ ] **Step 14: Manual gate — re-pull against the live bridge**

This produces a **new snapshot id**; it never edits an existing snapshot.

```bash
uv run pytest -m vm -v                                  # live Norgate audit still green
uv run python -m number7.ops.nightly
```

Expected: a new `data/snapshots/<db_date>/` whose `meta.json` has
`"bases": ["totalreturn", "capital"]`, `qc_report.json` free of `severity: "error"`,
`data/current` repointed, and the process exiting 0. Confirm the runtime increase is
tolerable and record it. If QC errors, **do not** promote — investigate first.

- [ ] **Step 15: Verify the promoted snapshot**

```bash
uv run python -c "
from number7.config import get_settings
from number7.data.snapshot import SnapshotPaths, current_snapshot, read_meta
from number7.data.store import load_price_panel
root = current_snapshot(get_settings()); m = read_meta(SnapshotPaths(root))
print(root.name, m.bases, m.n_price_rows)
df = load_price_panel(root, symbols=['AAPL'], start='2020-08-25', end='2020-09-02')
print(df[['date','px_close','tr_close','raw_close']].to_string(index=False))
"
```

Expected: `bases` lists both; across AAPL's 2020-08-31 4:1 split, `px_close` shows **no**
−75% step (it is split-adjusted) while `raw_close` drops from ~499 to ~129. This is the
empirical claim in spec §2 — confirm it on the real snapshot before building on it.

---

### Task 2: `PanelView` dual-basis extension and `build_panel`

The existing `close` field is **renamed**, not duplicated, so every call site is forced to
choose a basis explicitly. This task also fixes confirmed defect #1 (SPY is a buyable
candidate) and adds the `assetid` needed for §6.1's tie-break.

**Files:**
- Modify: `src/number7/engine/strategy.py:11-24` (`PanelView`)
- Modify: `src/number7/engine/live.py:13-25` (`build_panel`)
- Modify: `src/number7/engine/backtest.py:22-31,37` (cost inputs, return basis)
- Modify: `src/number7/validation/walkforward.py:66,85-93`, `src/number7/validation/causality.py:21-24`
- Modify: `src/number7/benchmarks/ew.py:17-23`, `src/number7/engine/strategy.py:65-93`
- Test: `tests/conftest.py` (new `make_panel` helper), `tests/test_strategy.py`,
  `tests/test_backtest.py`, `tests/test_calibration.py`, `tests/test_causality.py`,
  `tests/test_monkey.py`, `tests/test_walkforward.py`, `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `PRICE_COLS`, `SnapshotMeta.bases` (Task 1).
- Produces:
  - `PanelView(px_open, px_high, px_low, px_close, tr_close, raw_close, volume, in_index, assetid)` — all `pd.DataFrame` except `assetid: pd.Series`.
  - `PanelView.sessions -> pd.DatetimeIndex`, `PanelView.view_end -> pd.Timestamp`, `PanelView.masked_to(end) -> PanelView`.
  - `MissingBasisError(RuntimeError)` raised by `build_panel`.
  - `tests/conftest.py::make_panel(close, *, in_index=None, high=None, low=None, open_=None, tr_close=None, assetid=None) -> PanelView`.

- [ ] **Step 1: Write the failing PanelView tests**

Replace `tests/test_strategy.py::_view` with the shared helper and add the new assertions.

```python
# tests/test_strategy.py
import numpy as np
import pandas as pd

from number7.engine.strategy import StrategyManifest


def _view(make_panel):
    dates = pd.date_range("2026-06-01", periods=10, freq="B")
    close = pd.DataFrame(np.linspace(100, 110, 10)[:, None] * [1, 2, 3],
                         index=dates, columns=["A", "B", "C"])
    flags = pd.DataFrame(True, index=dates, columns=["A", "B", "C"])
    flags.loc[:, "C"] = False                             # C not in index
    return make_panel(close, in_index=flags)


def test_masked_to_hides_future_in_every_frame(make_panel):
    v = _view(make_panel)
    cut = v.sessions[4]
    m = v.masked_to(cut)
    assert m.view_end == cut
    for f in (m.px_open, m.px_high, m.px_low, m.px_close, m.tr_close,
              m.raw_close, m.volume, m.in_index):
        assert len(f) == 5 and f.index[-1] == cut
    pd.testing.assert_series_equal(m.assetid, v.assetid)   # not time-indexed
```

- [ ] **Step 2: Add the `make_panel` fixture**

`tests/conftest.py` — one helper so the six panel-building test files change by one line each.

```python
import numpy as np

from number7.engine.strategy import PanelView


def _make_panel(close: pd.DataFrame, *, in_index=None, high=None, low=None,
                open_=None, tr_close=None, assetid=None) -> PanelView:
    """Build a PanelView from a single close matrix. Signal basis (px_*) and P&L basis
    (tr_close) coincide unless overridden — fine for engine tests, NOT for basis tests."""
    idx, cols = close.index, close.columns
    return PanelView(
        px_open=close if open_ is None else open_,
        px_high=close * 1.01 if high is None else high,
        px_low=close * 0.99 if low is None else low,
        px_close=close,
        tr_close=close if tr_close is None else tr_close,
        raw_close=close,
        volume=pd.DataFrame(1e9, index=idx, columns=cols),
        in_index=(pd.DataFrame(True, index=idx, columns=cols)
                  if in_index is None else in_index),
        assetid=(pd.Series(np.arange(1.0, len(cols) + 1.0), index=cols)
                 if assetid is None else assetid),
    )


@pytest.fixture
def make_panel():
    return _make_panel
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_strategy.py -v`
Expected: FAIL — `PanelView.__init__() got an unexpected keyword argument 'px_open'`.

- [ ] **Step 4: Rewrite `PanelView`**

`src/number7/engine/strategy.py`. Construct explicitly with keywords in `masked_to` — the
old positional splat silently depends on field order, and there are now nine fields.

```python
@dataclass(frozen=True)
class PanelView:
    """Dual-basis point-in-time panel (spec §7). Basis assignment is normative:
    px_* (capital-adjusted) for every SIGNAL computation, tr_close for P&L and
    benchmarks, raw_close for fills, ADV and broker reconciliation. There is no
    field called `close` on purpose — every reader must name its basis."""

    px_open: pd.DataFrame
    px_high: pd.DataFrame
    px_low: pd.DataFrame
    px_close: pd.DataFrame
    tr_close: pd.DataFrame
    raw_close: pd.DataFrame
    volume: pd.DataFrame
    in_index: pd.DataFrame
    assetid: pd.Series          # symbol -> Norgate assetid; stable tie-break key (§6.1)

    @property
    def sessions(self) -> pd.DatetimeIndex:
        return self.px_close.index

    @property
    def view_end(self) -> pd.Timestamp:
        return self.px_close.index[-1]

    def masked_to(self, end: pd.Timestamp) -> "PanelView":
        return PanelView(
            px_open=self.px_open.loc[:end], px_high=self.px_high.loc[:end],
            px_low=self.px_low.loc[:end], px_close=self.px_close.loc[:end],
            tr_close=self.tr_close.loc[:end], raw_close=self.raw_close.loc[:end],
            volume=self.volume.loc[:end], in_index=self.in_index.loc[:end],
            assetid=self.assetid,          # not time-indexed: nothing to truncate
        )
```

Point `RandomTopN` and `LookaheadTrap` at the renamed frames (`view.px_close.columns`,
`view.px_close.loc[t]`, `self._full_close` built from `p.px_close`). Their `Slate` return
type comes in Task 3 — this step is the rename only.

- [ ] **Step 5: Run the test to verify it passes**

Run: `set -o pipefail && uv run pytest tests/test_strategy.py -v`
Expected: PASS.

- [ ] **Step 6: Write the failing `build_panel` tests**

```python
# tests/test_live_panel.py  (new file)
import pandas as pd
import pytest

from number7.data.snapshot import SnapshotPaths, read_meta
from number7.engine.live import MissingBasisError, build_panel


def test_build_panel_carries_both_bases_and_assetids(fake_snapshot):
    panel = build_panel(fake_snapshot)
    assert list(panel.px_close.columns) == ["AAPL", "ATVI", "SPY"]
    assert panel.tr_close.loc["2026-06-29", "AAPL"] > panel.px_close.loc["2026-06-29", "AAPL"]
    assert panel.raw_close.loc["2026-06-29", "AAPL"] < panel.px_close.loc["2026-06-29", "AAPL"]
    assert panel.assetid["AAPL"] == 1.0


def test_regime_instrument_is_not_a_constituent(fake_snapshot):
    """Confirmed defect #1: build_panel used to force in_index=True for extra_symbols,
    making SPY a buyable candidate and polluting the hold_top_pct denominator."""
    panel = build_panel(fake_snapshot)
    assert not panel.in_index["SPY"].any()
    assert panel.in_index["AAPL"].all()


def test_snapshot_without_price_basis_is_rejected(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    meta = read_meta(p)
    meta.bases = ["totalreturn"]
    p.meta.write_text(meta.model_dump_json(indent=2))
    with pytest.raises(MissingBasisError, match="capital"):
        build_panel(fake_snapshot)
```

- [ ] **Step 7: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_live_panel.py -v`
Expected: FAIL — `ImportError: cannot import name 'MissingBasisError'`.

- [ ] **Step 8: Rewrite `build_panel`**

`src/number7/engine/live.py`.

```python
from number7.data.snapshot import SnapshotPaths, read_meta

REQUIRED_BASES = ("totalreturn", "capital")


class MissingBasisError(RuntimeError):
    """The snapshot predates the dual-basis schema, so signals would be computed on the
    total-return basis and systematically tilted toward high-dividend names (spec §2)."""


def build_panel(snapshot_root: Path, start: str | None = None) -> PanelView:
    paths = SnapshotPaths(snapshot_root)
    meta = read_meta(paths)
    missing = [b for b in REQUIRED_BASES if b not in meta.bases]
    if missing:
        raise MissingBasisError(
            f"snapshot {snapshot_root.name} records bases {meta.bases}; missing {missing}. "
            "Re-sync with the dual-basis pull before running any signal code.")
    tidy = load_price_panel(snapshot_root, start=start)

    def piv(col: str) -> pd.DataFrame:
        return tidy.pivot(index="date", columns="symbol", values=col).sort_index()

    px_close = piv("px_close")
    membership = load_membership(snapshot_root)
    # in_index means ACTUAL point-in-time index membership. Extras (SPY) are deliberately
    # NOT flagged: the regime instrument must not be a buyable candidate, and must not
    # inflate the hold_top_pct denominator (spec §6.2, confirmed defect #1).
    flags = in_index_flags(membership, list(px_close.columns), px_close.index)
    meta_df = pd.read_parquet(paths.metadata).set_index("symbol")
    assetid = pd.to_numeric(meta_df["assetid"], errors="coerce") \
                .reindex(px_close.columns).astype(float)
    return PanelView(px_open=piv("px_open"), px_high=piv("px_high"), px_low=piv("px_low"),
                     px_close=px_close, tr_close=piv("tr_close"), raw_close=piv("raw_close"),
                     volume=piv("volume"), in_index=flags, assetid=assetid)
```

- [ ] **Step 9: Run it to verify it passes**

Run: `set -o pipefail && uv run pytest tests/test_live_panel.py -v`
Expected: PASS.

- [ ] **Step 10: Point the engine's return and cost bases at the right frames**

`src/number7/engine/backtest.py` — three edits, each a basis choice the rename now forces.

```python
def _one_way(cost_model: CostModel, panel: PanelView, asof: pd.Timestamp,
             sym: str, dw: float, equity: float) -> float:
    """Cost inputs (sigma, ADV) use data through `asof` = the SIGNAL date, not the
    execution session — the live path submits before t's close exists (§4.1 contract).
    Sigma is measured on the capital-adjusted basis (dividend drift is not volatility);
    ADV is a traded-notional quantity, so it uses raw price x raw volume."""
    sigma = float(np.log(panel.px_close[sym]).diff().loc[:asof].tail(63).std() or 0.0)
    if not np.isfinite(sigma):
        sigma = 0.0
    adv = float((panel.raw_close[sym] * panel.volume[sym]).loc[:asof].tail(20).mean())
    q_over_adv = 0.0 if not np.isfinite(adv) or adv <= 0 else abs(dw) * equity / adv
    return cost_model.one_way_cost(spread_est=0.0, q_over_adv=q_over_adv, sigma=sigma)
```

In `run_backtest`: `sessions = panel.sessions`, `rets = panel.tr_close.pct_change().fillna(0.0)`,
`w = pd.Series(0.0, index=panel.tr_close.columns)`, and the empty-result fallback
`pd.DataFrame(columns=panel.tr_close.columns)`.

- [ ] **Step 11: Update the remaining panel readers**

- `src/number7/validation/walkforward.py`: `sessions = panel.sessions`; `is_view.sessions`
  and `oos_view.sessions` in place of `is_view.close.index` / `oos_view.close.index`.
- `src/number7/validation/causality.py`: `panel.sessions` in the bounds check, the `cut`
  computation, and `compute_live_targets`' reindex target.
- `src/number7/benchmarks/ew.py`: `pd.Series(0.0, index=view.px_close.columns)`.
- `src/number7/engine/live.py::compute_live_targets`: `signal_date(panel.sessions, asof)`
  and `.reindex(panel.px_close.columns)`.

- [ ] **Step 12: Convert the six test panels to `make_panel`**

Each of `tests/test_backtest.py`, `tests/test_calibration.py`, `tests/test_causality.py`,
`tests/test_monkey.py`, `tests/test_walkforward.py` builds its `close` matrix already;
replace the `PanelView(...)` call with `make_panel(close)` (or `make_panel(close, in_index=ones)`
where the test builds custom flags) and take `make_panel` as a fixture argument. Inside those
tests, `view.close.columns` becomes `view.px_close.columns` and `panel.close.index` becomes
`panel.sessions`.

`tests/test_benchmark.py::test_ew_benchmark_holds_members_only` keeps asserting
`w["SPY"] == 0.0`; it now holds because `in_index["SPY"]` is False, not only because of the
benchmark's `exclude` tuple. Add one line proving the stronger property:

```python
    assert not build_panel(fake_snapshot).in_index["SPY"].any()
```

- [ ] **Step 13: Run the full offline suite**

Run: `set -o pipefail && uv run pytest 2>&1 | tail -20`
Expected: PASS, 88+ tests. `uv run ruff check src tests` clean.

- [ ] **Step 14: Commit**

```bash
git add src/number7 tests
git commit -m "feat(engine): carry both price bases on PanelView; stop flagging extras as constituents

PanelView now exposes px_open/px_high/px_low/px_close (signals), tr_close (P&L) and
raw_close (fills, ADV). The old `close` field is renamed rather than duplicated so every
call site has to name its basis - the engine's return stream is total-return, its cost
sigma is capital-adjusted, and its ADV is raw notional.

build_panel refuses a snapshot whose meta.bases lacks the capital basis, and no longer
forces in_index=True for extra_symbols: SPY was a buyable candidate and inflated the
hold_top_pct denominator (spec §6.2, confirmed defect #1).

PanelView.assetid carries the stable tie-break key required by spec §6.1."
```

---

### Task 3: `Slate` return type and the book-level validator

Change the **return type**, not the signature (spec §5.2). A bare `regime_on` boolean cannot
recover the budget-constrained fill: under regime-on the fill stops when equity is exhausted
(say rank 17), so a held name at rank 30 would be absent from an already-budgeted book and
the diff would sell it, whereas correct regime-off behaviour funds it.

**Files:**
- Modify: `src/number7/engine/strategy.py` (add `Slate`, change `Strategy`, update fixtures)
- Modify: `src/number7/benchmarks/ew.py:17-23`
- Modify: `src/number7/engine/backtest.py:56-58`, `src/number7/engine/live.py:32-34`
- Test: `tests/test_strategy.py`, `tests/test_backtest.py`, `tests/test_monkey.py`,
  `tests/test_walkforward.py`, `tests/test_benchmark.py`

**Interfaces:**
- Consumes: `PanelView` (Task 2), `validate_weights`.
- Produces:
  - `Slate(weights: pd.Series, rank: pd.Series, admit_new: bool)` — frozen dataclass.
  - `Strategy.target_weights(self, view: PanelView) -> Slate`.
  - `full_slate(weights: pd.Series) -> Slate` — helper for always-invested fixtures/benchmarks.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategy.py
import pytest

from number7.engine.strategy import RandomTopN, Slate, full_slate


def test_random_topn_emits_a_slate(make_panel):
    v = _view(make_panel)
    s1, s2 = RandomTopN(n=2, seed=7), RandomTopN(n=2, seed=7)
    a, b = s1.target_weights(v), s2.target_weights(v)
    assert isinstance(a, Slate) and a.admit_new is True
    pd.testing.assert_series_equal(a.weights, b.weights)
    assert (a.weights >= 0).all() and a.weights.sum() <= 1.0 + 1e-9
    assert "C" not in a.weights[a.weights > 0].index      # C is not a constituent
    held = a.weights[a.weights > 0].index
    assert a.rank.loc[held].notna().all()                 # every funded name is ranked
    assert a.rank.dropna().is_unique


def test_full_slate_ranks_by_descending_weight():
    w = pd.Series({"A": 0.2, "B": 0.5, "C": 0.0})
    s = full_slate(w)
    assert s.admit_new is True
    assert s.rank["B"] == 1.0 and s.rank["A"] == 2.0
    assert pd.isna(s.rank["C"])
```

- [ ] **Step 2: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_strategy.py -v`
Expected: FAIL — `ImportError: cannot import name 'Slate'`.

- [ ] **Step 3: Add `Slate`, `full_slate`, and change the protocol**

`src/number7/engine/strategy.py`.

```python
@dataclass(frozen=True)
class Slate:
    """What a strategy emits (spec §5.2). ABSOLUTE, unbudgeted weights for every ELIGIBLE
    name plus the rank vector over the full point-in-time constituent set, so the
    holdings-aware resolver can reconstruct the budget-constrained fill. Never normalized
    to sum 1 — normalizing would cancel risk_factor and destroy the emergent position count."""

    weights: pd.Series      # absolute ATR-parity weight for ALL eligible names
    rank: pd.Series         # 1-based raw rank over constituents; NaN where unrankable
    admit_new: bool         # the regime gate: allow_open_new_symbols


def full_slate(weights: pd.Series) -> Slate:
    """Slate for an always-invested strategy (benchmarks, null fixtures): rank follows
    descending weight, unfunded names are unranked."""
    funded = weights[weights > 0].sort_values(ascending=False, kind="mergesort")
    rank = pd.Series(np.nan, index=weights.index, dtype=float)
    rank[funded.index] = np.arange(1.0, len(funded) + 1.0)
    return Slate(weights=weights, rank=rank, admit_new=True)


class Strategy(Protocol):
    manifest: StrategyManifest

    def target_weights(self, view: PanelView) -> Slate: ...
```

`RandomTopN.target_weights` and `LookaheadTrap.target_weights` end with `return full_slate(w)`.
`EqualWeightIndex.target_weights` (`src/number7/benchmarks/ew.py`) likewise.

- [ ] **Step 4: Unwrap the slate at the two engine call sites**

Resolution proper arrives in Task 5; for now both sites take `.weights` so the suite stays
green and the change is reviewable on its own.

`src/number7/engine/backtest.py`:

```python
            slate = strategy.target_weights(view)
            target = validate_weights(
                slate.weights.reindex(w.index).fillna(0.0),
                name=strategy.manifest.name)
```

`src/number7/engine/live.py`:

```python
    slate = strategy.target_weights(view)
    return validate_weights(
        slate.weights.reindex(panel.px_close.columns).fillna(0.0),
        name=strategy.manifest.name)
```

- [ ] **Step 5: Update the in-test strategies**

`AllInA` (`tests/test_backtest.py`), `AlwaysLong` (`tests/test_walkforward.py`) and
`BestDrift` (`tests/test_monkey.py`) each build a `w` Series; each now returns
`full_slate(w)`. Import `full_slate` in those three files.

- [ ] **Step 6: Run the suite**

Run: `set -o pipefail && uv run pytest 2>&1 | tail -20`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add src/number7 tests
git commit -m "feat(engine): strategies emit a Slate instead of a weight vector

Slate carries absolute unbudgeted ATR-parity weights for every eligible name, the rank
vector over the full constituent set, and the regime gate. A bare regime_on boolean
cannot recover the budget-constrained fill: a held name below the fill cut-off would be
absent from an already-budgeted book and the diff would sell it, when correct regime-off
behaviour funds it (spec §5.2).

The signature stays target_weights(view) - the strategy remains a pure function of the
panel, which is what keeps truncate-and-compare a TOTAL causality proof."
```

---

### Task 4: `strategies/sizing.py` — `SizingConfig`, `resolve_book`, drift band

The holdings-aware layer, shared verbatim with the future ETF sleeve, called identically by
`run_backtest` and `compute_live_targets`. Ordering is normative (spec §8.2) — do not
reorder to "optimize" the stranded-budget effect described in the interpretation notes.

**Files:**
- Create: `src/number7/strategies/__init__.py`, `src/number7/strategies/sizing.py`
- Test: `tests/test_sizing.py`

**Interfaces:**
- Consumes: `Slate`, `validate_weights`, `PanelView` (Tasks 2–3).
- Produces:
  - `SizingConfig(sleeve_equity: float, position_cap=0.10, min_position_dollars=1000.0, gross_max=1.0, drift_band=0.05, max_positions=30, forced_resize_periods=8)` — frozen dataclass.
  - `resolve_book(slate: Slate, current: pd.Series, config: SizingConfig, stale_periods: pd.Series | None = None) -> pd.Series`
  - `apply_drift_band(target: pd.Series, current: pd.Series, config: SizingConfig, stale_periods: pd.Series | None = None) -> pd.Series`
  - `validate_book(w: pd.Series, config: SizingConfig, name: str = "book") -> pd.Series`
  - `holdings_from_shares(shares: Mapping[str, float], raw_close: pd.Series, sleeve_equity: float) -> pd.Series`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sizing.py
import numpy as np
import pandas as pd
import pytest

from number7.engine.strategy import Slate
from number7.strategies.sizing import (SizingConfig, apply_drift_band,
                                       holdings_from_shares, resolve_book, validate_book)

SYMS = ["A", "B", "C", "D"]


def _slate(weights: dict, admit_new: bool = True) -> Slate:
    w = pd.Series(0.0, index=SYMS)
    w.update(pd.Series(weights))
    funded = w[w > 0]
    rank = pd.Series(np.nan, index=SYMS, dtype=float)
    rank[funded.index] = np.arange(1.0, len(funded) + 1.0)   # dict order = rank order
    return Slate(weights=w, rank=rank, admit_new=admit_new)


def _cfg(**kw) -> SizingConfig:
    return SizingConfig(sleeve_equity=50_000.0, **kw)


def _flat() -> pd.Series:
    return pd.Series(0.0, index=SYMS)


def test_budgeted_fill_skips_the_marginal_name_and_stops():
    slate = _slate({"A": 0.5, "B": 0.4, "C": 0.3, "D": 0.05})
    book = resolve_book(slate, _flat(), _cfg(position_cap=1.0))
    assert book["A"] == pytest.approx(0.5) and book["B"] == pytest.approx(0.4)
    assert book["C"] == 0.0 and book["D"] == 0.0     # C does not fit; the walk terminates


def test_max_positions_truncates_the_fill():
    slate = _slate({"A": 0.1, "B": 0.1, "C": 0.1, "D": 0.1})
    book = resolve_book(slate, _flat(), _cfg(max_positions=2))
    assert int((book > 0).sum()) == 2 and book["A"] > 0 and book["B"] > 0


def test_position_cap_clips_and_can_strand_budget():
    """Spec §8.2 orders fill (2) BEFORE cap (3): the 0.40 name consumes 0.40 of budget
    and is then clipped to 0.10. The stranded 0.30 is expected, not a bug."""
    slate = _slate({"A": 0.4, "B": 0.4, "C": 0.4})
    book = resolve_book(slate, _flat(), _cfg())
    assert book["A"] == pytest.approx(0.10) and book["B"] == pytest.approx(0.10)
    assert book["C"] == 0.0
    assert book.sum() == pytest.approx(0.20)


def test_gross_normalization_scales_down_proportionally():
    slate = _slate({"A": 0.6, "B": 0.4})
    book = resolve_book(slate, _flat(), _cfg(position_cap=1.0, gross_max=0.5))
    assert book.sum() == pytest.approx(0.5)
    assert book["A"] / book["B"] == pytest.approx(1.5)


def test_floor_is_applied_after_normalization():
    """A $1,050 position pushed below $1,000 by normalization must be dropped (§8.2.5)."""
    slate = _slate({"A": 0.9, "B": 0.021})
    cfg = _cfg(position_cap=1.0, gross_max=0.5, min_position_dollars=1000.0)
    book = resolve_book(slate, _flat(), cfg)
    assert book["B"] == 0.0                      # 0.021 * 50k = $1,050 -> ~$1,022 -> $1,022?
    assert book["A"] > 0


def test_regime_off_restricts_candidates_to_still_eligible_holdings():
    slate = _slate({"A": 0.2, "B": 0.2}, admit_new=False)
    current = pd.Series({"A": 0.0, "B": 0.15, "C": 0.10, "D": 0.0})
    book = resolve_book(slate, current, _cfg(position_cap=1.0))
    assert book["B"] == pytest.approx(0.2)       # held AND still eligible -> re-sized UP
    assert book["A"] == 0.0                      # eligible but not held -> not admitted
    assert book["C"] == 0.0                      # held but no longer eligible -> exited


def test_drift_band_holds_inside_and_trades_outside():
    cfg = _cfg(drift_band=0.05)
    target = pd.Series({"A": 0.10, "B": 0.10, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.097, "B": 0.093, "C": 0.0, "D": 0.0})   # -3% / -7%
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == pytest.approx(0.097)      # inside band -> keep current, no order
    assert out["B"] == pytest.approx(0.10)       # outside band -> trade to target


def test_entries_and_exits_always_execute():
    cfg = _cfg(drift_band=0.99)
    target = pd.Series({"A": 0.10, "B": 0.0, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.0, "B": 0.10, "C": 0.0, "D": 0.0})
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == pytest.approx(0.10) and out["B"] == 0.0


def test_retention_that_would_breach_position_cap_forces_the_trade():
    """The exact silent-breach case in spec §8.3: clipped to 0.10, current 0.104,
    |delta|/target = 4% <= 5% band -> would be kept at 0.104 and never caught, because
    validate_weights does not check position_cap."""
    cfg = _cfg(position_cap=0.10, drift_band=0.05)
    target = pd.Series({"A": 0.10, "B": 0.0, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.104, "B": 0.0, "C": 0.0, "D": 0.0})
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == pytest.approx(0.10)
    validate_book(out, cfg)                       # must not raise


def test_retention_that_would_breach_gross_max_forces_trades():
    cfg = _cfg(position_cap=1.0, gross_max=1.0, drift_band=0.05)
    target = pd.Series({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    current = pd.Series({"A": 0.26, "B": 0.26, "C": 0.26, "D": 0.26})   # +4% each
    out = apply_drift_band(target, current, cfg)
    assert out.sum() <= 1.0 + 1e-9
    validate_book(out, cfg)


def test_forced_resize_after_n_stale_periods():
    cfg = _cfg(drift_band=0.05, forced_resize_periods=3)
    target = pd.Series({"A": 0.10, "B": 0.10, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.098, "B": 0.098, "C": 0.0, "D": 0.0})
    stale = pd.Series({"A": 3, "B": 0, "C": 0, "D": 0})
    out = apply_drift_band(target, current, cfg, stale)
    assert out["A"] == pytest.approx(0.10)       # stale -> forced re-size
    assert out["B"] == pytest.approx(0.098)      # fresh -> held


def test_validate_book_rejects_cap_and_gross_breaches():
    cfg = _cfg()
    with pytest.raises(ValueError, match="position_cap"):
        validate_book(pd.Series({"A": 0.2}), cfg)
    with pytest.raises(ValueError, match="gross_max"):
        validate_book(pd.Series({"A": 0.1, "B": 0.1}), _cfg(gross_max=0.15))


def test_resolved_book_always_passes_its_own_validator():
    """Property test over random slates: no path through resolve_book may emit a book
    that breaches the contract (spec §12 contract-wide)."""
    rng = np.random.default_rng(0)
    cfg = _cfg()
    for _ in range(200):
        w = pd.Series(rng.uniform(0.0, 0.35, len(SYMS)), index=SYMS)
        rank = pd.Series(rng.permutation(np.arange(1.0, len(SYMS) + 1.0)), index=SYMS)
        slate = Slate(weights=w, rank=rank, admit_new=bool(rng.integers(2)))
        current = pd.Series(rng.uniform(0.0, 0.2, len(SYMS)), index=SYMS)
        validate_book(resolve_book(slate, current, cfg), cfg)


def test_holdings_come_from_shares_and_the_signal_date_close():
    """Spec §8.4: never broker market value - the live path runs on the morning of T and
    must mark at T-1's official close, exactly as the backtest does."""
    raw = pd.Series({"A": 100.0, "B": 50.0, "C": 10.0, "D": 1.0})
    out = holdings_from_shares({"A": 25, "B": 40}, raw, sleeve_equity=50_000.0)
    assert out["A"] == pytest.approx(0.05) and out["B"] == pytest.approx(0.04)
    assert out["C"] == 0.0
```

Fix the inline arithmetic in `test_floor_is_applied_after_normalization` while writing it:
pre-normalization the book is `{A: 0.9, B: 0.021}` summing to 0.921; scaling to
`gross_max=0.5` multiplies by 0.5429, so B becomes 0.0114 = $570 < $1,000 and is dropped —
the assertion `book["B"] == 0.0` is correct; delete the trailing comment.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `set -o pipefail && uv run pytest tests/test_sizing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'number7.strategies'`.

- [ ] **Step 3: Write `sizing.py`**

```python
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from number7.engine.strategy import Slate, validate_weights

_TOL = 1e-12


@dataclass(frozen=True)
class SizingConfig:
    """Book-resolution configuration (spec §8.1). `sleeve_equity` is the CURRENT sleeve
    equity supplied per call — a fixed book_equity constant is wrong after P&L and wrong
    once the sleeve holds only part of the total book."""

    sleeve_equity: float
    position_cap: float = 0.10          # §8 max single position
    min_position_dollars: float = 1000.0
    gross_max: float = 1.0              # §8 no leverage
    drift_band: float = 0.05
    max_positions: int = 30
    forced_resize_periods: int = 8      # §8.3: re-size a band-held name after N periods


def validate_book(w: pd.Series, config: SizingConfig, name: str = "book") -> pd.Series:
    """validate_weights PLUS the two limits it does not check. `validate_weights` alone
    tests finite/>=0/sum<=1, so a name retained at 0.104 against a 0.10 cap passes
    undetected (spec §8.3)."""
    validate_weights(w, name=name)
    over = w[w > config.position_cap + 1e-9]
    if len(over):
        raise ValueError(f"{name} breaches position_cap {config.position_cap}: "
                         f"{[(s, round(float(over[s]), 4)) for s in over.index[:3]]}")
    total = float(w.sum())
    if total > config.gross_max + 1e-9:
        raise ValueError(f"{name} gross {total:.4f} > gross_max {config.gross_max}")
    return w


def apply_drift_band(target: pd.Series, current: pd.Series, config: SizingConfig,
                     stale_periods: pd.Series | None = None) -> pd.Series:
    """Relative band on names held and still held: keep `current` when
    |target - current| / target <= drift_band. Entries and exits always execute.

    Post-band re-validation is MANDATORY: the band runs after normalization and can
    re-violate both limits (spec §8.3). A relative band also bites five times harder on a
    10% position than a 2% one, and a name can drift within band indefinitely — hence the
    forced re-size after `forced_resize_periods`."""
    current = current.reindex(target.index).fillna(0.0)
    stale = (pd.Series(0, index=target.index) if stale_periods is None
             else stale_periods.reindex(target.index).fillna(0))
    both = (target > 0) & (current > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = (target - current).abs() / target.where(target > 0)
    keep = both & (rel <= config.drift_band) & (stale < config.forced_resize_periods)
    out = target.where(~keep, current)

    breach = keep & (out > config.position_cap + 1e-9)      # retention breaches the cap
    out[breach] = target[breach]
    keep = keep & ~breach
    while float(out.sum()) > config.gross_max + 1e-9 and bool(keep.any()):
        worst = (out - target).where(keep).idxmax()          # largest upward retention
        out[worst], keep[worst] = target[worst], False
    return out


def resolve_book(slate: Slate, current: pd.Series, config: SizingConfig,
                 stale_periods: pd.Series | None = None) -> pd.Series:
    """Admission -> budgeted top-down fill -> cap -> gross normalization -> floor ->
    drift band -> re-validate (spec §8.2). Order is normative.

    Called identically by run_backtest and compute_live_targets. `current` is always
    state_at_signal (T-1), never state_at_fill: live trading cannot know T's closing
    weights when the MOC order is submitted that morning (spec §5.3)."""
    idx = slate.weights.index
    current = current.reindex(idx).fillna(0.0)

    # 1. admission — regime-off funds retained names, it does not freeze the book
    eligible = slate.weights > 0
    if not slate.admit_new:
        eligible &= current > 0

    # 2. budgeted top-down fill; the marginal name is SKIPPED, not partially filled,
    #    and the walk terminates there so rank priority is never inverted
    ranked = slate.rank.where(eligible).dropna().sort_values(kind="mergesort").index
    target = pd.Series(0.0, index=idx)
    used, n = 0.0, 0
    for sym in ranked:
        if n >= config.max_positions:
            break
        w = float(slate.weights[sym])
        if used + w > config.gross_max + _TOL:
            break
        target[sym], used, n = w, used + w, n + 1

    # 3. position cap
    target = target.clip(upper=config.position_cap)

    # 4. gross normalization
    gross = float(target.sum())
    if gross > config.gross_max:
        target *= config.gross_max / gross

    # 5. floor, AFTER all scalars — normalization can push a surviving $1,050 position
    #    below $1,000. Dropping only lowers the sum, so one pass IS the fixed point;
    #    the shortfall stays in cash.
    floor_w = config.min_position_dollars / config.sleeve_equity
    target[target < floor_w] = 0.0

    # 6. drift band, then re-validate
    return validate_book(apply_drift_band(target, current, config, stale_periods),
                         config, name="resolved_book")


def holdings_from_shares(shares: Mapping[str, float], raw_close: pd.Series,
                         sleeve_equity: float) -> pd.Series:
    """Live-path `current` (spec §8.4): broker SHARE COUNTS x the snapshot's T-1 official
    close / sleeve equity — never broker market value. The backtest marks holdings at
    T-1's close while the live path runs on the morning of T; broker market value would
    mark after the open, so golden replay would pass on a fixture while the live path
    silently diverged intraday.

    Callers must NOT invoke this with a partial or stale broker snapshot: stale broker
    truth degrades to hold-state / no trades, because a misread `current_i > 0` mask
    converts a designed hold-through-drawdown into an accidental full exit."""
    held = pd.Series(shares, dtype=float).reindex(raw_close.index).fillna(0.0)
    return (held * raw_close / sleeve_equity).fillna(0.0)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `set -o pipefail && uv run pytest tests/test_sizing.py -v`
Expected: PASS (14 tests).

- [ ] **Step 5: Commit**

```bash
git add src/number7/strategies tests/test_sizing.py
git commit -m "feat(strategies): add the shared holdings-aware book resolver

resolve_book performs admission, the budgeted top-down fill, position cap, gross
normalization, the dollar floor and the drift band, in that normative order (spec §8.2),
and is called identically by run_backtest and compute_live_targets. It lives outside the
strategy so target_weights(view) stays a pure function of the panel and truncate-and-
compare remains a total causality proof.

Two behaviours are pinned because the spec left them open: the fill terminates at the
marginal name rather than continuing to lower-ranked names that would fit, and the floor
is a single pass with the shortfall left in cash.

validate_book adds the position_cap and gross_max checks validate_weights lacks, and the
drift band forces the trade for any retention that would breach either - the exact silent
0.104-against-a-0.10-cap breach in spec §8.3."
```

---

### Task 5: Engine wiring — signal-time state, resolver, cash rate, parity

The engine must stop conflating the two holdings states (spec §5.3). `state_at_signal` is the
book as of T−1's close and is what `resolve_book` receives; `state_at_fill` is the book marked
through T and is used *ex post* for the post-fill book. Turnover and costs are measured against
`state_at_signal`, because that is the order the live path actually submits.

**Files:**
- Modify: `src/number7/engine/backtest.py` (whole `run_backtest` loop, `BacktestResult`)
- Modify: `src/number7/engine/live.py:28-34` (`compute_live_targets`)
- Test: `tests/test_backtest.py`, `tests/test_live_parity.py`

**Interfaces:**
- Consumes: `PanelView`, `Slate`, `SizingConfig`, `resolve_book`, `validate_book`.
- Produces:
  - `run_backtest(strategy, panel, rebalance_dates, cost_model, *, sizing: SizingConfig | None = None, initial: float = 1.0, cash_annual_rate: float = 0.0, start: pd.Timestamp | None = None, initial_weights: pd.Series | None = None, initial_stale: pd.Series | None = None, record_slates: bool = False) -> BacktestResult`
  - `BacktestResult(equity, weights, turnover, costs, rebalance_dates, state_at_signal: pd.DataFrame, stale_periods: pd.DataFrame, equity_at_signal: pd.Series, delisting_exits: pd.Series, final_weights: pd.Series, final_stale: pd.Series, slates: dict[pd.Timestamp, Slate] | None)`
  - `compute_live_targets(strategy, panel, asof, *, current: pd.Series | None = None, sizing: SizingConfig | None = None, stale_periods: pd.Series | None = None) -> pd.Series`
- `sizing=None` means **passthrough**: the slate's weights are used as-is after
  `validate_weights`. Benchmarks and null fixtures keep Phase-1 behaviour; the sleeve always
  supplies a `SizingConfig`.

- [ ] **Step 1: Write the failing engine tests**

```python
# tests/test_backtest.py — additions
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.strategy import Slate, StrategyManifest
from number7.strategies.sizing import SizingConfig


class FixedSlate:
    """Emits a constant absolute weight for A and B, always admitting."""

    manifest = StrategyManifest(name="fixed", family="test", origin="human", params={})

    def __init__(self, weights: dict) -> None:
        self._w = weights

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w.update(pd.Series(self._w))
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank[list(self._w)] = np.arange(1.0, len(self._w) + 1.0)
        return Slate(weights=w, rank=rank, admit_new=True)


def test_state_at_signal_is_the_prior_close_book(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[7]])
    res = run_backtest(AllInA(), panel, rb, CostModel(min_half_spread_bps=0.0))
    assert res.state_at_signal.loc[rb[0]].sum() == pytest.approx(0.0)   # still in cash
    assert res.state_at_signal.loc[rb[1]]["A"] == pytest.approx(1.0)
    # equity used for sizing is T-1's, never T's
    sig = panel.sessions[panel.sessions.get_loc(rb[1]) - 1]
    assert res.equity_at_signal.loc[rb[1]] == pytest.approx(res.equity.loc[sig])


def test_cash_earns_the_pinned_rate(make_panel):
    panel = _panel(make_panel)
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([]), CostModel(),
                       cash_annual_rate=0.04)
    n = len(panel.sessions)
    assert res.equity.iloc[-1] == pytest.approx((1.04 ** (1 / 252)) ** n, rel=1e-9)


def test_resolver_runs_when_sizing_is_supplied(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2]])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, min_position_dollars=0.0)
    res = run_backtest(FixedSlate({"A": 0.9}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg)
    assert res.weights.loc[rb[0], "A"] == pytest.approx(0.30)     # capped by the resolver


def test_drift_band_retention_produces_zero_turnover(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[3]])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0,
                       drift_band=0.50)
    res = run_backtest(FixedSlate({"A": 0.5}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg)
    assert res.turnover.loc[rb[1]] == pytest.approx(0.0, abs=1e-12)


def test_stale_counter_increments_on_hold_and_resets_on_trade(make_panel):
    panel = _panel(make_panel)
    rb = pd.DatetimeIndex(panel.sessions[2:6])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0,
                       drift_band=0.50, forced_resize_periods=99)
    res = run_backtest(FixedSlate({"A": 0.5}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=cfg)
    assert res.stale_periods.loc[rb[1], "A"] == 0     # entry traded at rb[0]
    assert res.stale_periods.loc[rb[3], "A"] == 2     # held through rb[1] and rb[2]


def test_start_limits_the_loop_and_initial_weights_seed_it(make_panel):
    panel = _panel(make_panel)
    seed = pd.Series(0.0, index=panel.px_close.columns)
    seed["A"] = 1.0
    res = run_backtest(AllInA(), panel, pd.DatetimeIndex([]), CostModel(),
                       start=panel.sessions[5], initial_weights=seed)
    assert res.equity.loc[:panel.sessions[4]].isna().all()
    assert res.equity.iloc[-1] == pytest.approx(1.01 ** (len(panel.sessions) - 5), rel=1e-9)
    assert res.final_weights["A"] == pytest.approx(1.0)


def test_delisted_holding_is_exited_at_the_next_rebalance_and_counted(make_panel):
    dates = pd.date_range("2026-01-05", periods=10, freq="B")
    close = pd.DataFrame({"A": 100.0, "B": 50.0}, index=dates)
    close.loc[dates[5]:, "A"] = np.nan                    # A stops trading
    panel = make_panel(close)
    rb = pd.DatetimeIndex([dates[2], dates[8]])
    res = run_backtest(FixedSlate({"A": 1.0}), panel, rb, CostModel(min_half_spread_bps=0.0),
                       sizing=SizingConfig(sleeve_equity=1.0, position_cap=1.0,
                                           min_position_dollars=0.0))
    assert res.weights.loc[rb[1]].sum() == pytest.approx(0.0)   # A is unrankable -> exited
    assert int(res.delisting_exits.loc[rb[1]]) == 1
    assert np.isfinite(res.equity.iloc[-1])
```

`_panel` gains a `make_panel` argument: `def _panel(make_panel, n=15): ... return make_panel(close)`.
Update the three existing tests in the file to pass the fixture through.

- [ ] **Step 2: Run them to verify they fail**

Run: `set -o pipefail && uv run pytest tests/test_backtest.py -v`
Expected: FAIL — `BacktestResult` has no `state_at_signal`, `run_backtest()` got an
unexpected keyword argument `sizing`.

- [ ] **Step 3: Rewrite `run_backtest`**

`src/number7/engine/backtest.py`.

```python
from dataclasses import dataclass, replace

from number7.engine.strategy import PanelView, Slate, Strategy, validate_weights
from number7.strategies.sizing import SizingConfig, resolve_book


@dataclass
class BacktestResult:
    equity: pd.Series
    weights: pd.DataFrame                 # resolved book decided at each rebalance
    turnover: pd.Series
    costs: pd.Series
    rebalance_dates: pd.DatetimeIndex
    state_at_signal: pd.DataFrame         # holdings as of T-1 close (what the resolver saw)
    stale_periods: pd.DataFrame           # consecutive band-held periods, as of T-1
    equity_at_signal: pd.Series           # sleeve equity as of T-1 close
    delisting_exits: pd.Series            # held names with no quote at the signal date
    final_weights: pd.Series              # post-loop book, for walk-forward fold carry-over
    final_stale: pd.Series
    slates: dict[pd.Timestamp, Slate] | None = None


def run_backtest(strategy: Strategy, panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                 cost_model: CostModel, *, sizing: SizingConfig | None = None,
                 initial: float = 1.0, cash_annual_rate: float = 0.0,
                 start: pd.Timestamp | None = None,
                 initial_weights: pd.Series | None = None,
                 initial_stale: pd.Series | None = None,
                 record_slates: bool = False) -> BacktestResult:
    """Causal weekly-cadence engine (blueprint §4.1). `sizing=None` is passthrough: the
    slate's weights are the book, which is what benchmarks and null fixtures want. With a
    SizingConfig, the same resolve_book the live path calls decides the book.

    `start` limits the SIMULATED sessions without truncating the information set — signals
    still read the full history behind them. Walk-forward uses it with `initial_weights` so
    an OOS fold inherits the IS end-state instead of opening flat.

    KNOWN OPTIMISTIC ASSUMPTION (spec §9): the loop sets w = target after observing T's
    return, assuming exact closing-weight attainment from a morning-submitted MOC order.
    Not a signal leak; the paper phase will measure it."""
    sessions = panel.sessions
    cols = panel.tr_close.columns
    rets = panel.tr_close.pct_change().fillna(0.0)
    cash_daily = (1.0 + cash_annual_rate) ** (1.0 / 252.0) - 1.0
    loop = sessions if start is None else sessions[sessions >= start]

    equity = pd.Series(np.nan, index=sessions, dtype=float)
    decided: dict[pd.Timestamp, pd.Series] = {}
    signal_state: dict[pd.Timestamp, pd.Series] = {}
    signal_stale: dict[pd.Timestamp, pd.Series] = {}
    signal_equity: dict[pd.Timestamp, float] = {}
    delisted: dict[pd.Timestamp, int] = {}
    turnover: dict[pd.Timestamp, float] = {}
    costs: dict[pd.Timestamp, float] = {}
    slates: dict[pd.Timestamp, Slate] = {}

    w = (pd.Series(0.0, index=cols) if initial_weights is None
         else initial_weights.reindex(cols).fillna(0.0))
    stale = (pd.Series(0, index=cols, dtype=int) if initial_stale is None
             else initial_stale.reindex(cols).fillna(0).astype(int))
    eq = initial
    rb = set(rebalance_dates)

    for t in loop:
        state_at_signal, eq_at_signal = w.copy(), eq   # T-1 close: captured BEFORE the
        cash = 1.0 - float(w.sum())                    # earn/drift lines (spec §5.3)
        eq *= float(1.0 + (w * rets.loc[t]).sum() + cash * cash_daily)
        if float(w.sum()) > 0:
            grown = w * (1.0 + rets.loc[t])
            port = float(grown.sum() + cash * (1.0 + cash_daily))
            w = grown / port
        if t in rb and t != sessions[0]:      # first session has no signal date - skip
            sig = signal_date(sessions, t)
            view = panel.masked_to(sig)
            slate = strategy.target_weights(view)
            if record_slates:
                slates[t] = slate
            if sizing is None:
                target = validate_weights(slate.weights.reindex(cols).fillna(0.0),
                                          name=strategy.manifest.name)
            else:
                cfg = replace(sizing, sleeve_equity=eq_at_signal)
                target = resolve_book(slate, state_at_signal, cfg,
                                      stale).reindex(cols).fillna(0.0)
            # Orders are sized from T-1 information — that is exactly what the live path
            # submits, so a drift-band retention costs nothing and moves nothing.
            dw = (target - state_at_signal).abs()
            c = float(sum(_one_way(cost_model, panel, sig, s, float(dw[s]), eq) * float(dw[s])
                          for s in dw.index[dw > 0]))
            if c >= 1.0:      # costs consuming the whole book = broken cost model/sizing
                raise RuntimeError(f"rebalance cost fraction {c:.3f} >= 1.0 at {t.date()} - "
                                   "cost model or position sizing is misconfigured")
            eq *= 1.0 - c
            traded = dw > 1e-12
            stale = pd.Series(np.where(traded | (target <= 0), 0, stale + 1),
                              index=cols, dtype=int)
            signal_state[t], signal_stale[t] = state_at_signal, stale.copy()
            signal_equity[t] = eq_at_signal
            delisted[t] = int(((state_at_signal > 0)
                               & panel.tr_close.loc[sig].isna()).sum())
            turnover[t], costs[t], decided[t] = float(dw.sum()), c, target
            w = target.copy()
        equity.loc[t] = eq

    return BacktestResult(
        equity=equity,
        weights=pd.DataFrame(decided).T if decided else pd.DataFrame(columns=cols),
        turnover=pd.Series(turnover, dtype=float),
        costs=pd.Series(costs, dtype=float),
        rebalance_dates=pd.DatetimeIndex(sorted(decided)),   # executed only (skips excluded)
        state_at_signal=pd.DataFrame(signal_state).T if signal_state
        else pd.DataFrame(columns=cols),
        stale_periods=pd.DataFrame(signal_stale).T if signal_stale
        else pd.DataFrame(columns=cols),
        equity_at_signal=pd.Series(signal_equity, dtype=float),
        delisting_exits=pd.Series(delisted, dtype=float),
        final_weights=w,
        final_stale=stale,
        slates=slates if record_slates else None,
    )
```

Note `signal_stale[t]` records the **post-trade** counter for date `t`, which is the counter
the *next* rebalance consumes; the test above reads it with that meaning.

- [ ] **Step 4: Run the engine tests**

Run: `set -o pipefail && uv run pytest tests/test_backtest.py -v`
Expected: PASS. `test_engine_timing_and_compounding` still holds — turnover against
`state_at_signal` is 1.0 at the first rebalance (from cash) and 0.0 at the second.

- [ ] **Step 5: Write the failing parity test**

`tests/test_live_parity.py` — parity must now hold **through resolution and the band**.

```python
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.live import build_panel, compute_live_targets
from number7.engine.strategy import RandomTopN, Slate, StrategyManifest
from number7.strategies.sizing import SizingConfig, holdings_from_shares


class TwoNames:
    manifest = StrategyManifest(name="two", family="test", origin="human", params={})

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w["AAPL"], w["ATVI"] = 0.6, 0.5
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank["AAPL"], rank["ATVI"] = 1.0, 2.0
        return Slate(weights=w, rank=rank, admit_new=True)


def test_golden_replay_engine_equals_live_path(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[3]])
    res = run_backtest(RandomTopN(n=1, seed=3), panel, rb, CostModel())
    for t in rb:
        live = compute_live_targets(RandomTopN(n=1, seed=3), panel, asof=t)
        pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)


def test_golden_replay_through_resolution_and_band(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.sessions[2], panel.sessions[3]])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, min_position_dollars=0.0,
                       drift_band=0.05)
    res = run_backtest(TwoNames(), panel, rb, CostModel(), sizing=cfg)
    for t in rb:
        live = compute_live_targets(
            TwoNames(), panel, asof=t,
            current=res.state_at_signal.loc[t],
            sizing=replace(cfg, sleeve_equity=float(res.equity_at_signal.loc[t])),
            # stale_periods is recorded POST-trade for each date, so the counter the
            # resolver consumed at t is the previous rebalance's row.
            stale_periods=res.stale_periods.shift(1).fillna(0).loc[t])
        pd.testing.assert_series_equal(res.weights.loc[t], live, check_names=False)


def test_live_holdings_are_built_from_shares_not_market_value(fake_snapshot):
    panel = build_panel(fake_snapshot)
    t = panel.sessions[3]
    sig = panel.sessions[2]
    cur = holdings_from_shares({"AAPL": 10}, panel.raw_close.loc[sig], sleeve_equity=10_000.0)
    assert cur["AAPL"] == pytest.approx(10 * float(panel.raw_close.loc[sig, "AAPL"]) / 10_000.0)
```

Feeding the shifted counter rather than adding a twelfth `BacktestResult` field is
deliberate: the pre-trade counter is derivable from what the result already carries.

- [ ] **Step 6: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_live_parity.py -v`
Expected: FAIL — `compute_live_targets()` got an unexpected keyword argument `current`.

- [ ] **Step 7: Extend `compute_live_targets`**

`src/number7/engine/live.py`.

```python
def compute_live_targets(strategy: Strategy, panel: PanelView, asof: pd.Timestamp, *,
                         current: pd.Series | None = None,
                         sizing: SizingConfig | None = None,
                         stale_periods: pd.Series | None = None) -> pd.Series:
    """THE Phase-2 order-service entry point: weights to execute at `asof`'s close,
    decided strictly from data <= the prior session (blueprint §4.1 timing contract).

    `current` MUST be built with holdings_from_shares() from broker share counts and the
    signal date's official close (spec §8.4), and MUST reflect a healthy broker snapshot —
    stale or degraded broker truth degrades to hold-state / no trades, never to treating an
    unknown position as flat."""
    cols = panel.px_close.columns
    view = panel.masked_to(signal_date(panel.sessions, asof))
    slate = strategy.target_weights(view)
    if sizing is None:
        return validate_weights(slate.weights.reindex(cols).fillna(0.0),
                                name=strategy.manifest.name)
    cur = (pd.Series(0.0, index=cols) if current is None
           else current.reindex(cols).fillna(0.0))
    return resolve_book(slate, cur, sizing, stale_periods).reindex(cols).fillna(0.0)
```

- [ ] **Step 8: Run the parity tests and the full suite**

Run: `set -o pipefail && uv run pytest 2>&1 | tail -20`
Expected: PASS. Then `uv run ruff check src tests` — clean.

- [ ] **Step 9: Commit**

```bash
git add src/number7/engine tests/test_backtest.py tests/test_live_parity.py
git commit -m "feat(engine): separate signal-time state from fill-time state and run the resolver

run_backtest now captures state_at_signal and sleeve equity at the TOP of session t,
before the earn/drift lines, and hands both to resolve_book - live trading cannot know
T's closing weights when the MOC order is submitted that morning (spec §5.3). Turnover and
costs are measured against state_at_signal, which is the order actually submitted, so a
drift-band retention costs and moves exactly nothing.

Also adds: an explicit cash_annual_rate (the engine earned zero on cash, worth roughly
1-2%/yr against a book that is often part-cash, spec §11.3); `start` + initial_weights so a
walk-forward fold can inherit its IS end-state; a delisting-exit counter; and slate
recording behind a flag for the closed-loop causality check.

compute_live_targets gains current/sizing/stale_periods and calls the SAME resolve_book,
so golden replay now pins parity through resolution and the drift band."
```

---

### Task 6: Walk-forward fold state (gauntlet fix 1)

Confirmed defect #2. `walkforward.py` builds a fresh strategy per fold and `run_backtest`
starts in cash, so an OOS fold opening in regime-off can never buy and returns ~0 —
systematically depressing bear folds and biasing WFE against exactly the periods the regime
gate exists for.

**Files:**
- Modify: `src/number7/validation/walkforward.py:56-104`
- Test: `tests/test_walkforward.py`

**Interfaces:**
- Consumes: `run_backtest(..., start=, initial_weights=, initial_stale=, sizing=)`, `BacktestResult.final_weights`, `.final_stale`.
- Produces: `walk_forward(strategy_factory, panel, protocol, cost_model, *, sizing=None, initial=1.0, cash_annual_rate=0.0) -> WFReport` (unchanged return type).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_walkforward.py — additions
import numpy as np
import pandas as pd

from number7.engine.strategy import Slate, StrategyManifest, full_slate
from number7.strategies.sizing import SizingConfig


class BuysOnlyEarly:
    """Opens positions only in the first half of the panel; afterwards it emits the same
    weights but refuses to admit new names — the regime-off shape that used to zero out
    every OOS fold."""

    manifest = StrategyManifest(name="early", family="test", origin="human", params={})

    def __init__(self, cutoff: pd.Timestamp) -> None:
        self._cutoff = cutoff

    def target_weights(self, view) -> Slate:
        s = full_slate(pd.Series({c: 1.0 if c == view.px_close.columns[0] else 0.0
                                  for c in view.px_close.columns}))
        return Slate(weights=s.weights, rank=s.rank,
                     admit_new=bool(view.view_end <= self._cutoff))


def test_oos_fold_inherits_the_is_end_state():
    panel = _drift_panel(years=8)
    cutoff = panel.sessions[len(panel.sessions) // 3]
    protocol = WFProtocol(train_years=3, test_months=6, step_months=6, min_windows=8)
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0)
    report = walk_forward(lambda: BuysOnlyEarly(cutoff), panel, protocol,
                          CostModel(min_half_spread_bps=0.0), sizing=cfg)
    late = [w for w in report.windows if w["test"][0] > str(cutoff.date())]
    assert late, "test needs folds that open after the cutoff"
    assert all(abs(w["oos_annual_profit"]) > 1e-6 for w in late)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_walkforward.py -v`
Expected: FAIL — `walk_forward()` got an unexpected keyword argument `sizing`; and with
that removed, every late fold reports `oos_annual_profit == 0.0` because it opens flat.

- [ ] **Step 3: Carry the fold state**

`src/number7/validation/walkforward.py` — signature and the two `run_backtest` calls.

```python
def walk_forward(strategy_factory: Callable[[], Strategy], panel: PanelView,
                 protocol: WFProtocol, cost_model: CostModel, *,
                 sizing: SizingConfig | None = None, initial: float = 1.0,
                 cash_annual_rate: float = 0.0) -> WFReport:
```

```python
        is_res = run_backtest(strategy_factory(), is_view, is_rb, cost_model,
                              sizing=sizing, initial=initial,
                              cash_annual_rate=cash_annual_rate, start=start)
        oos_view = panel.masked_to(test_end)
        oos_sessions = oos_view.sessions[oos_view.sessions > train_end]
        oos_rb = rb_global[(rb_global > train_end) & (rb_global <= test_end)]
        # Carry the IS end-state into OOS. A fresh fold starting in cash can never buy
        # while the regime gate is off, so bear folds returned ~0 and biased WFE against
        # precisely the periods the gate exists to handle (spec §10.1).
        oos_res = run_backtest(strategy_factory(), oos_view, oos_rb, cost_model,
                               sizing=sizing, initial=initial,
                               cash_annual_rate=cash_annual_rate,
                               start=oos_sessions[0] if len(oos_sessions) else None,
                               initial_weights=is_res.final_weights,
                               initial_stale=is_res.final_stale)
```

Guard the empty case: `if len(oos_sessions) < 2: start = start + pd.DateOffset(months=protocol.step_months); continue` — hoist that check above the OOS run so `oos_sessions[0]` is always safe, and drop `len(oos_eq) < 2` from the later combined check (keep `len(is_sessions) < 2`).

The IS run also takes `start=start` so its own equity path is confined to the window; before
this, sessions ahead of `start` had no rebalances and contributed a flat 1.0 prefix, so
`.loc[is_sessions]` masked the difference. It now genuinely starts at the window.

- [ ] **Step 4: Run the walk-forward tests**

Run: `set -o pipefail && uv run pytest tests/test_walkforward.py -v`
Expected: PASS, including the pre-existing `test_walk_forward_on_steady_drift`
(`wfe ≈ 1.0`) and `test_overlapping_windows_rejected`.

- [ ] **Step 5: Commit**

```bash
git add src/number7/validation/walkforward.py tests/test_walkforward.py
git commit -m "fix(validation): carry the IS end-state into each OOS walk-forward fold

Every fold used to open flat, so an OOS segment beginning with the regime gate off could
never buy and returned ~0 - biasing WFE against bear folds, which is the opposite of what
a walk-forward is for (spec §10.1, confirmed defect #2). The OOS run now starts at the
first OOS session with the IS run's final weights and stale counters.

walk_forward also gains sizing/initial/cash_annual_rate passthrough so a fold is resolved
with exactly the config the candidate ships with."
```

---

### Task 7: Closed-loop causality check (gauntlet fix 3)

Confirmed gauntlet gap. Fixed-`current` truncate-and-compare proves *pointwise* panel purity
at one holdings point. A path-dependent, part-cash strategy needs the trajectory compared too.

**Files:**
- Modify: `src/number7/validation/causality.py`
- Test: `tests/test_causality.py`

**Interfaces:**
- Consumes: `run_backtest(..., record_slates=True)`, `BacktestResult.slates`, `.state_at_signal`, `.weights`.
- Produces: `closed_loop_violations(strategy_from_panel: Callable[[PanelView], Strategy], panel: PanelView, rebalance_dates: pd.DatetimeIndex, cost_model: CostModel, *, sizing: SizingConfig | None = None, truncate_last_n: int = 5) -> list[str]` — human-readable violation strings, empty when clean.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_causality.py — additions
import numpy as np
import pandas as pd

from number7.engine.costs import CostModel
from number7.engine.strategy import LookaheadTrap, RandomTopN, Slate, StrategyManifest
from number7.strategies.sizing import SizingConfig
from number7.validation.causality import causality_violations, closed_loop_violations


class TrajectoryLeak:
    """Pure at any single point, but its ADMISSION gate reads the last bar of its stored
    panel — so the trajectory diverges even though pointwise weights can match."""

    manifest = StrategyManifest(name="traj_leak", family="trap", origin="human", params={})

    def __init__(self, panel) -> None:
        self._end = panel.px_close.iloc[-1].mean()

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w[view.px_close.columns[0]] = 0.5
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank[view.px_close.columns[0]] = 1.0
        return Slate(weights=w, rank=rank,
                     admit_new=bool(view.px_close.iloc[-1].mean() < self._end))


def test_closed_loop_clean_for_a_causal_strategy(make_panel):
    panel = _walk_panel(make_panel, n=40)
    rb = pd.DatetimeIndex(panel.sessions[5::5])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0)
    assert closed_loop_violations(lambda p: RandomTopN(n=1, seed=5), panel, rb,
                                  CostModel(), sizing=cfg, truncate_last_n=5) == []


def test_closed_loop_catches_a_trajectory_leak(make_panel):
    panel = _walk_panel(make_panel, n=40)
    rb = pd.DatetimeIndex(panel.sessions[5::5])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0)
    bad = closed_loop_violations(lambda p: TrajectoryLeak(p), panel, rb,
                                 CostModel(), sizing=cfg, truncate_last_n=10)
    assert bad
```

`_walk_panel` takes `make_panel` and `n` (default 10) and returns `make_panel(close)`; update
its two existing callers.

- [ ] **Step 2: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_causality.py -v`
Expected: FAIL — `ImportError: cannot import name 'closed_loop_violations'`.

- [ ] **Step 3: Implement the closed-loop check**

Append to `src/number7/validation/causality.py`.

```python
from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.strategies.sizing import SizingConfig


def closed_loop_violations(strategy_from_panel: Callable[[PanelView], Strategy],
                           panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                           cost_model: CostModel, *, sizing: SizingConfig | None = None,
                           truncate_last_n: int = 5) -> list[str]:
    """Trajectory-level truncate-and-compare (spec §10.3). causality_violations() proves
    panel purity at ONE holdings point; a path-dependent, part-cash strategy also has to
    reach the same STATE. Runs the full and truncated simulations from the same initial
    state and compares every overlapping slate, resolved book and transition."""
    sessions = panel.sessions
    if not 0 < truncate_last_n < len(sessions):
        raise ValueError(f"truncate_last_n={truncate_last_n} must be in "
                         f"[1, {len(sessions) - 1}] for this panel")
    cut = sessions[-(truncate_last_n + 1)]
    truncated = panel.masked_to(cut)
    common = pd.DatetimeIndex([t for t in rebalance_dates if t <= cut])
    kw = dict(cost_model=cost_model, sizing=sizing, record_slates=True)
    full = run_backtest(strategy_from_panel(panel), panel, common, **kw)
    trunc = run_backtest(strategy_from_panel(truncated), truncated, common, **kw)

    bad: list[str] = []
    for t in common:
        if t not in full.slates or t not in trunc.slates:
            bad.append(f"{t.date()}: rebalance executed in only one run")
            continue
        a, b = full.slates[t], trunc.slates[t]
        cols = b.weights.index
        if a.admit_new != b.admit_new:
            bad.append(f"{t.date()}: admit_new {a.admit_new} != {b.admit_new}")
        if not a.weights[cols].round(12).equals(b.weights.round(12)):
            bad.append(f"{t.date()}: slate weights differ")
        if not a.rank[cols].round(12).equals(b.rank.round(12)):
            bad.append(f"{t.date()}: slate rank differs")
        for label, fa, fb in (("state_at_signal", full.state_at_signal, trunc.state_at_signal),
                              ("resolved_book", full.weights, trunc.weights)):
            if not fa.loc[t, cols].round(12).equals(fb.loc[t].round(12)):
                bad.append(f"{t.date()}: {label} differs")
    if not full.equity.loc[:cut].round(12).equals(trunc.equity.loc[:cut].round(12)):
        bad.append(f"equity trajectory differs on the overlap through {cut.date()}")
    return bad
```

- [ ] **Step 4: Run the causality tests**

Run: `set -o pipefail && uv run pytest tests/test_causality.py -v`
Expected: PASS — including the pre-existing `test_lookahead_trap_is_caught`.

- [ ] **Step 5: Run the full suite and commit**

Run: `set -o pipefail && uv run pytest 2>&1 | tail -20 && uv run ruff check src tests`
Expected: PASS, clean.

```bash
git add src/number7/validation/causality.py tests/test_causality.py
git commit -m "feat(validation): add a closed-loop causality check

Truncate-and-compare with fixed holdings proves panel purity at one point. A path-dependent,
part-cash strategy also has to reach the same STATE, so this runs the full and truncated
simulations from the same initial state and compares every overlapping slate, resolved book,
signal-time state and the equity trajectory (spec §10.3).

The pointwise check stays: the strategy is still a pure function of the panel, so
causality_violations remains a total proof of the decision function."
```

---

### Task 8: `strategies/clenow.py` — the strategy

Stateless, pure function of the panel. Every computation reads the capital-adjusted basis.

**Files:**
- Create: `src/number7/strategies/clenow.py`
- Test: `tests/test_clenow.py`

**Interfaces:**
- Consumes: `PanelView` (`px_open/px_high/px_low/px_close`, `in_index`, `assetid`), `Slate`, `StrategyManifest`.
- Produces:
  - `ANN_FACTOR = 250`, `ATR_BURN_IN_MULT = 5`
  - `ClenowParams(lookback=90, atr_window=20, ma_filter=100, regime_ma=200, gap_threshold=0.15, risk_factor=0.001, hold_top_pct=0.20, regime_symbol="SPY", use_r2=True, use_regime=True, use_gap_filter=True, equal_weight=False, equal_weight_size=0.04)` — frozen dataclass
  - `slope_r2(log_px: np.ndarray) -> tuple[np.ndarray, np.ndarray]`
  - `wilder_atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame, window: int) -> pd.Series`
  - `ClenowMomentum(params: ClenowParams, shuffle_seed: int | None = None)` with `.manifest` and `.target_weights(view) -> Slate`

- [ ] **Step 1: Write the failing known-answer tests**

```python
# tests/test_clenow.py
import numpy as np
import pandas as pd
import pytest

from number7.strategies.clenow import (ANN_FACTOR, ATR_BURN_IN_MULT, ClenowMomentum,
                                       ClenowParams, slope_r2, wilder_atr)

P = ClenowParams()
NEED = max(P.lookback, P.ma_filter, P.atr_window * ATR_BURN_IN_MULT + 1)   # 101


def _series(n: int, daily: float, start: float = 100.0) -> np.ndarray:
    return start * np.exp(daily * np.arange(n))


def _panel(make_panel, *, movers: dict[str, float], n: int = 400,
           regime_daily: float = 0.0005, regime_start: float = 300.0):
    """Log-linear universe plus SPY. `movers` maps symbol -> daily log drift."""
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    data = {s: _series(n, d) for s, d in movers.items()}
    data["SPY"] = _series(n, regime_daily, regime_start)
    close = pd.DataFrame(data, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False                      # regime instrument is no constituent
    return make_panel(close, in_index=flags, high=close * 1.01, low=close * 0.99,
                      open_=close)


def test_planted_log_linear_trend_is_recovered_analytically():
    b = 0.0007
    slope, r2 = slope_r2(np.log(_series(90, b))[:, None])
    assert slope[0] == pytest.approx(b, rel=1e-12)
    assert r2[0] == pytest.approx(1.0, abs=1e-12)
    assert float(np.expm1(slope[0] * ANN_FACTOR)) == pytest.approx(np.expm1(b * 250))


def test_constant_log_price_has_undefined_r2():
    slope, r2 = slope_r2(np.log(np.full((90, 1), 50.0)))
    assert np.isnan(r2[0])


def test_wilder_atr_matches_the_pinned_recursion():
    n = 60
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    high = pd.DataFrame({"A": np.full(n, 102.0)}, index=idx)
    low = pd.DataFrame({"A": np.full(n, 100.0)}, index=idx)
    close = pd.DataFrame({"A": np.full(n, 101.0)}, index=idx)
    # constant bars: TR = 2.0 every day after the first, so seed = 2.0 and the
    # recursion (19 * 2 + 2) / 20 = 2.0 is a fixed point
    assert float(wilder_atr(high, low, close, 20)["A"]) == pytest.approx(2.0)

    close2 = close.copy()
    close2.iloc[-1] = 110.0                     # last bar gaps up: TR = |110 - 101| = 9
    got = float(wilder_atr(high, low, close2, 20)["A"])
    assert got == pytest.approx((19 * 2.0 + max(2.0, abs(102 - 101), abs(100 - 101))) / 20)


def test_wilder_atr_uses_the_mean_seed_not_the_first_true_range():
    n = 40
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(0)
    close = pd.DataFrame({"A": 100 + np.cumsum(rng.normal(0, 1, n))}, index=idx)
    high, low = close + 1.0, close - 1.0
    prev = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev).abs(), (low - prev).abs())).iloc[1:]
    tail = tr.tail(P.atr_window * ATR_BURN_IN_MULT)
    manual = float(tail.iloc[:P.atr_window].mean().iloc[0])
    for v in tail["A"].to_numpy()[P.atr_window:]:
        manual = (19 * manual + float(v)) / 20
    assert float(wilder_atr(high, low, close, 20)["A"]) == pytest.approx(manual, rel=1e-12)


def test_gap_filter_fires_at_151bp_not_149(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001})
    o = panel.px_open.copy()
    o.iloc[-30, o.columns.get_loc("A")] *= 1.151     # inside the 90-session window
    o.iloc[-30, o.columns.get_loc("B")] *= 1.149
    strat = ClenowMomentum(ClenowParams(hold_top_pct=1.0))
    slate = strat.target_weights(make_panel(panel.px_close, in_index=panel.in_index,
                                            high=panel.px_high, low=panel.px_low, open_=o))
    assert slate.weights["A"] == 0.0
    assert slate.weights["B"] > 0.0


def test_ties_break_on_assetid_not_ticker_order(make_panel):
    panel = _panel(make_panel, movers={"ZZZ": 0.001, "AAA": 0.001})
    aid = pd.Series({"ZZZ": 10.0, "AAA": 99.0, "SPY": 3.0})
    v = make_panel(panel.px_close, in_index=panel.in_index, high=panel.px_high,
                   low=panel.px_low, open_=panel.px_open, assetid=aid)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)
    assert slate.rank["ZZZ"] < slate.rank["AAA"]     # identical scores, lower assetid wins
```

- [ ] **Step 2: Write the failing eligibility / regime / candidate-set tests**

```python
def test_short_history_embedded_nan_and_nonpositive_close_are_ineligible(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001},
                   n=NEED + 5)
    close = panel.px_close.copy()
    close.iloc[:-40, close.columns.get_loc("B")] = np.nan       # < NEED valid bars
    close.iloc[-50, close.columns.get_loc("C")] = np.nan        # embedded NaN
    close.iloc[-60, close.columns.get_loc("D")] = -1.0          # non-positive
    v = make_panel(close, in_index=panel.in_index, high=close * 1.01, low=close * 0.99,
                   open_=close)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)
    assert slate.weights[["B", "C", "D"]].eq(0.0).all()
    assert slate.weights["A"] > 0.0
    assert np.isfinite(slate.weights.to_numpy()).all()


def test_zero_atr_never_produces_an_infinite_weight(make_panel):
    n = 400
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    close = pd.DataFrame({"FLAT": np.full(n, 100.0), "A": _series(n, 0.001),
                          "SPY": _series(n, 0.0005, 300.0)}, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False
    v = make_panel(close, in_index=flags, high=close, low=close, open_=close)   # ATR == 0
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0)).target_weights(v)
    assert slate.weights["FLAT"] == 0.0
    assert np.isfinite(slate.weights.to_numpy()).all()


def test_regime_warmup_is_an_explicit_off_branch(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001}, n=NEED + 10)
    # NEED + 10 < regime_ma = 200, so SMA200 is undefined
    slate = ClenowMomentum(ClenowParams()).target_weights(panel)
    assert slate.admit_new is False


def test_regime_gate_flips_on_the_sma200_crossing(make_panel):
    up = _panel(make_panel, movers={"A": 0.001, "B": 0.001}, regime_daily=0.0008)
    down = _panel(make_panel, movers={"A": 0.001, "B": 0.001}, regime_daily=-0.0008)
    assert ClenowMomentum(ClenowParams()).target_weights(up).admit_new is True
    assert ClenowMomentum(ClenowParams()).target_weights(down).admit_new is False


def test_missing_regime_instrument_fails_safe(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001})
    v = make_panel(panel.px_close.drop(columns=["SPY"]),
                   in_index=panel.in_index.drop(columns=["SPY"]))
    assert ClenowMomentum(ClenowParams()).target_weights(v).admit_new is False


def test_regime_instrument_and_non_constituents_are_never_candidates(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.001 + i * 1e-5 for i in range(10)})
    slate = ClenowMomentum(ClenowParams(hold_top_pct=0.20)).target_weights(panel)
    assert slate.weights["SPY"] == 0.0 and pd.isna(slate.rank["SPY"])
    # denominator is the 10 constituents, not 11: floor(0.20 * 10) = 2 funded names
    assert int((slate.weights > 0).sum()) == 2


def test_ma_filter_excludes_a_name_below_its_sma100(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001})
    close = panel.px_close.copy()
    close.iloc[-1, close.columns.get_loc("A")] *= 0.5     # last close under SMA100
    v = make_panel(close, in_index=panel.in_index, high=close * 1.01, low=close * 0.99,
                   open_=close)
    slate = ClenowMomentum(ClenowParams(hold_top_pct=1.0, use_gap_filter=False)) \
        .target_weights(v)
    assert slate.weights["A"] == 0.0


def test_weights_are_absolute_atr_parity_not_normalized(make_panel):
    panel = _panel(make_panel, movers={"A": 0.001, "B": 0.001, "C": 0.001, "D": 0.001})
    p = ClenowParams(hold_top_pct=1.0, use_gap_filter=False)
    slate = ClenowMomentum(p).target_weights(panel)
    funded = slate.weights[slate.weights > 0]
    assert len(funded) == 4
    assert funded.sum() != pytest.approx(1.0)        # never normalized (spec §6.5)
    atr = wilder_atr(panel.px_high, panel.px_low, panel.px_close, p.atr_window)
    expected = p.risk_factor * panel.px_close.iloc[-1]["A"] / atr["A"]
    assert funded["A"] == pytest.approx(expected, rel=1e-12)


def test_shuffle_seed_is_a_function_of_the_date_not_the_call_count(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.001 + i * 1e-5 for i in range(20)})
    a, b = ClenowMomentum(ClenowParams(), shuffle_seed=7), ClenowMomentum(ClenowParams(),
                                                                          shuffle_seed=7)
    _ = a.target_weights(panel.masked_to(panel.sessions[-5]))   # burn a call on `a` only
    pd.testing.assert_series_equal(a.target_weights(panel).rank,
                                   b.target_weights(panel).rank)
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `set -o pipefail && uv run pytest tests/test_clenow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'number7.strategies.clenow'`.

- [ ] **Step 4: Write the regression and ATR helpers**

`src/number7/strategies/clenow.py`.

```python
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from number7.engine.strategy import PanelView, Slate, StrategyManifest

ANN_FACTOR = 250            # PINNED (spec OQ-2). NOT a parameter: the exponential is applied
# before the R^2 multiply, so varying it REORDERS names. Excluded from the searched space.
ATR_BURN_IN_MULT = 5        # PINNED burn-in: ATR is recursed over atr_window * 5 true ranges
# after the seed, so the value is not seed-dominated and the known-answer test has a
# unique answer (spec §6.5).


def slope_r2(log_px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS of each column of `log_px` on the ORDINAL session index 0..n-1 (spec §6.1).
    Ordinal rather than calendar spacing is intentional and matches the published method —
    do not "fix" it.

    R^2 here is a SMOOTHNESS HEURISTIC, not a significance measure: regressing a near-random
    walk on time is textbook spurious regression and a driftless walk has substantial
    expected R^2 over 90 sessions. That is intentional in the published system. Nobody
    should later upgrade it to a t-statistic or p-value gate."""
    n = log_px.shape[0]
    xc = np.arange(n, dtype=float)
    xc -= xc.mean()
    sxx = float((xc ** 2).sum())
    yc = log_px - log_px.mean(axis=0)
    slope = (xc[:, None] * yc).sum(axis=0) / sxx
    ss_tot = (yc ** 2).sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        r2 = np.where(ss_tot > 0, 1.0 - (ss_tot - slope ** 2 * sxx) / ss_tot, np.nan)
    return slope, r2          # constant log-price -> ss_tot == 0 -> R^2 NaN -> ineligible


def wilder_atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
               window: int) -> pd.Series:
    """Latest ATR per column with Wilder smoothing, PINNED (spec §6.5):
    seed ATR_n = mean(TR_1..TR_n), then ATR_t = ((n-1) * ATR_{t-1} + TR_t) / n.
    Simple-mean smoothing is a robustness DIAGNOSTIC, not a parameter — Wilder's
    alpha = 1/n implies an effective span near 2n, a materially different system.

    All three inputs must share one basis; mixing an adjusted close with raw high/low
    manufactures true ranges around every corporate action."""
    prev = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev).abs(), (low - prev).abs()))
    tr = tr.iloc[1:].tail(window * ATR_BURN_IN_MULT)      # first bar has no prev close
    if len(tr) < window:
        return pd.Series(np.nan, index=close.columns)
    base = tr.iloc[window - 1:].copy()
    base.iloc[0] = tr.iloc[:window].mean()                # pinned seed
    return base.ewm(alpha=1.0 / window, adjust=False).mean().iloc[-1]
```

`ewm(alpha=1/n, adjust=False)` seeded with the mean reproduces the recursion exactly;
that equivalence is what `test_wilder_atr_uses_the_mean_seed_not_the_first_true_range` pins.

- [ ] **Step 5: Write the strategy**

```python
@dataclass(frozen=True)
class ClenowParams:
    lookback: int = 90
    atr_window: int = 20
    ma_filter: int = 100
    regime_ma: int = 200
    gap_threshold: float = 0.15          # OVERNIGHT gap definition (spec §6.2)
    risk_factor: float = 0.001           # 10bp of equity per position PER UNIT OF ATR
    hold_top_pct: float = 0.20
    regime_symbol: str = "SPY"
    # Diagnostic switches (spec §11.2 ablations). NOT searched parameters.
    use_r2: bool = True
    use_regime: bool = True
    use_gap_filter: bool = True
    equal_weight: bool = False
    equal_weight_size: float = 0.04


class ClenowMomentum:
    """Clenow equity momentum (KB-02, KB-08, KB-11 §9a), STATELESS: a pure function of the
    panel. Admission, budgeting, caps, floor and the drift band live in sizing.resolve_book,
    which is what keeps truncate-and-compare a total causality proof (spec §5.2).

    `shuffle_seed` turns the strategy into the MATCHED monkey null (spec §10.2): the score
    vector is permuted among scoreable constituents, so ranking information is destroyed
    while eligibility filters, the regime gate, ATR sizing and resolution stay identical.
    The RNG is seeded on (seed, date) so the null is a pure function of the date — not the
    call-count-dependent construction in RandomTopN (spec §15)."""

    def __init__(self, params: ClenowParams, shuffle_seed: int | None = None) -> None:
        self.p = params
        self.shuffle_seed = shuffle_seed
        name = "clenow" if shuffle_seed is None else f"clenow_shuffled_{shuffle_seed}"
        self.manifest = StrategyManifest(
            name=name, family="null" if shuffle_seed is not None else "clenow_momentum",
            origin="human", params={**asdict(params), "ann_factor": ANN_FACTOR,
                                    "atr_burn_in_mult": ATR_BURN_IN_MULT},
            reentry_blackout_days=0)   # recorded decision, Clenow-faithful (spec §6.6)

    @property
    def _need(self) -> int:
        return max(self.p.lookback, self.p.ma_filter,
                   self.p.atr_window * ATR_BURN_IN_MULT + 1)

    def target_weights(self, view: PanelView) -> Slate:
        p, cols = self.p, view.px_close.columns
        weights = pd.Series(0.0, index=cols)
        rank_out = pd.Series(np.nan, index=cols, dtype=float)

        members = view.in_index.iloc[-1]
        names = list(members.index[members])          # constituents only: the regime
        if not names:                                 # instrument and every other extra
            return Slate(weights, rank_out, self._admit(view))   # are excluded (§6.2)
        px = view.px_close[names]
        if len(px) < self._need:
            return Slate(weights, rank_out, self._admit(view))

        # --- preconditions (§6.3): no silent NaN path into ranking ---
        tail = px.tail(self._need)
        valid = tail.notna().all() & (tail > 0).all()

        # --- score over the whole constituent set, THEN qualifiers (§6.2) ---
        lb = np.log(px.tail(p.lookback).to_numpy(dtype=float))
        slope, r2 = slope_r2(lb)
        ann = np.expm1(slope * ANN_FACTOR)
        raw = ann * r2 if p.use_r2 else ann
        score = pd.Series(raw, index=names).where(valid)
        if self.shuffle_seed is not None:
            rng = np.random.default_rng([self.shuffle_seed, view.view_end.toordinal()])
            scored = score.dropna().index
            score.loc[scored] = rng.permutation(score.loc[scored].to_numpy())

        aid = view.assetid.reindex(names).astype(float).fillna(np.inf)
        order = pd.DataFrame({"score": score, "aid": aid}).sort_values(
            ["score", "aid"], ascending=[False, True], kind="mergesort", na_position="last")
        rank = pd.Series(np.arange(1.0, len(order) + 1.0), index=order.index)
        rank[score.isna()] = np.nan          # unscoreable names are unrankable, not rank 1
        rank_out[names] = rank.reindex(names)

        # --- qualifiers, applied AFTER ranking: a name that fails a filter does not
        # promote the names below it (§6.2) ---
        cutoff = math.floor(p.hold_top_pct * len(names))
        q = valid & rank.reindex(names).le(cutoff)
        q &= px.iloc[-1] > px.tail(p.ma_filter).mean()
        if p.use_gap_filter:
            gap = (view.px_open[names] / px.shift(1) - 1.0).abs().tail(p.lookback)
            q &= ~(gap > p.gap_threshold).any()

        m = p.atr_window * ATR_BURN_IN_MULT + 1
        atr = wilder_atr(view.px_high[names].tail(m), view.px_low[names].tail(m),
                         px.tail(m), p.atr_window)
        q &= atr.gt(0.0).fillna(False)                # zero/NaN ATR -> never an infinite

        elig = list(q.fillna(False).index[q.fillna(False)])   # position
        if elig:
            if p.equal_weight:
                weights[elig] = p.equal_weight_size
            else:
                # ABSOLUTE, not proportional (§6.5). risk_factor is 10bp of equity per
                # position PER UNIT OF ATR; the resulting weight depends on close/ATR,
                # which varies enormously across names. Normalizing here would cancel
                # risk_factor and destroy the emergent position count.
                weights[elig] = (p.risk_factor * px.iloc[-1][elig] / atr[elig]).astype(float)
        return Slate(weights=weights, rank=rank_out, admit_new=self._admit(view))

    def _admit(self, view: PanelView) -> bool:
        """Regime gate (§6.4). Semantics are precisely allow_open_new_symbols = False —
        NOT "no buy orders" and NOT "the book never grows": retained names are still
        re-sized by current ATR parity, which can increase share counts in a downtrend.

        Warm-up is an EXPLICIT branch, not a NaN side effect: `NaN > x` is False, which
        would fall into regime-off by accident rather than by design. No hysteresis — the
        gate is entry-only, which bounds whipsaw cost."""
        p = self.p
        if not p.use_regime:
            return True
        if p.regime_symbol not in view.px_close.columns:
            return False                       # fail-safe: no regime series, no new names
        tail = view.px_close[p.regime_symbol].tail(p.regime_ma)
        if len(tail) < p.regime_ma or not bool(tail.notna().all()):
            return False                       # warm-up
        return bool(tail.iloc[-1] > tail.mean())
```

- [ ] **Step 6: Run the strategy tests**

Run: `set -o pipefail && uv run pytest tests/test_clenow.py -v`
Expected: PASS (18 tests).

- [ ] **Step 7: Add the leaky-variant causality test**

```python
# tests/test_clenow.py — additions
from number7.engine.costs import CostModel
from number7.strategies.sizing import SizingConfig
from number7.validation.causality import causality_violations, closed_loop_violations


class LeakyClenow(ClenowMomentum):
    """DELIBERATELY CHEATS: scores on the last bar of the stored panel instead of the
    view's last bar. Must be caught by both causality harnesses."""

    def __init__(self, params, full_px):
        super().__init__(params)
        self._full = full_px

    def target_weights(self, view):
        patched = type(view)(**{**view.__dict__, "px_close": self._full})
        return super().target_weights(patched)


def test_leaky_clenow_variant_is_caught(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.0005 * (i + 1) for i in range(6)})
    rb = pd.DatetimeIndex(panel.sessions[-40::10])
    assert causality_violations(lambda p: LeakyClenow(ClenowParams(), panel.px_close),
                                panel, rb, truncate_last_n=15)


def test_clenow_is_causal_pointwise_and_closed_loop(make_panel):
    panel = _panel(make_panel, movers={f"S{i}": 0.0005 * (i + 1) for i in range(6)})
    rb = pd.DatetimeIndex(panel.sessions[-40::10])
    cfg = SizingConfig(sleeve_equity=50_000.0)
    assert causality_violations(lambda p: ClenowMomentum(ClenowParams()), panel, rb,
                                truncate_last_n=15) == []
    assert closed_loop_violations(lambda p: ClenowMomentum(ClenowParams()), panel, rb,
                                  CostModel(), sizing=cfg, truncate_last_n=15) == []


def test_cross_snapshot_stability_of_the_decision(make_panel):
    """A future dividend rescales pre-event adjusted levels; slope, R^2, MA relations, gap
    ratios and close/ATR are all invariant to a multiplicative factor, so the decision for
    a fixed historical signal date must not move (spec §12)."""
    panel = _panel(make_panel, movers={f"S{i}": 0.0005 * (i + 1) for i in range(6)})
    later = make_panel(panel.px_close * 1.037, in_index=panel.in_index,
                       high=panel.px_high * 1.037, low=panel.px_low * 1.037,
                       open_=panel.px_open * 1.037)
    a = ClenowMomentum(ClenowParams()).target_weights(panel)
    b = ClenowMomentum(ClenowParams()).target_weights(later)
    pd.testing.assert_series_equal(a.rank, b.rank)
    pd.testing.assert_series_equal(a.weights, b.weights)
    assert a.admit_new == b.admit_new
```

If `LeakyClenow`'s panel-patching proves awkward against the frozen dataclass, use
`dataclasses.replace(view, px_close=self._full)` instead — same effect, less indirection.

- [ ] **Step 8: Run and commit**

Run: `set -o pipefail && uv run pytest tests/test_clenow.py -v && uv run ruff check src tests`
Expected: PASS, clean.

```bash
git add src/number7/strategies/clenow.py tests/test_clenow.py
git commit -m "feat(strategies): add the Clenow momentum strategy

Stateless: target_weights(view) -> Slate, a pure function of the panel, with every signal
read off the capital-adjusted basis. Ranks the whole point-in-time constituent set first and
applies qualifiers afterwards, so a name failing the gap or MA filter never promotes the
names below it. Ties break on assetid, never ticker order.

Pinned: ann_factor = 250 (excluded from the searched space - the exponential precedes the
R^2 multiply, so varying it reorders names); Wilder ATR with a mean seed and an
atr_window * 5 burn-in; the overnight gap definition; regime warm-up as an explicit
fail-safe branch rather than a NaN side effect.

Weights are ABSOLUTE ATR parity, never normalized - normalizing would cancel risk_factor
and destroy the emergent position count that makes the regime gate de-risking.

shuffle_seed produces the matched monkey null for spec §10.2, seeded on (seed, date) so it
is a pure function of the date."
```

---

### Task 9: Matched monkey null (gauntlet fix 2)

Confirmed defect #3. `monkey.py` uses `RandomTopN`, which is always fully invested and
equal-weight, against a candidate that is often part-cash and ATR-sized — so the null is
measuring cash exposure, not ranking skill.

**Files:**
- Modify: `src/number7/validation/monkey.py`
- Test: `tests/test_monkey.py`

**Interfaces:**
- Consumes: `ClenowMomentum(params, shuffle_seed=...)`, `run_backtest(..., sizing=)`.
- Produces: `monkey_test(candidate, panel, rebalance_dates, cost_model, *, null_factory: Callable[[int], Strategy] | None = None, sizing: SizingConfig | None = None, initial: float = 1.0, cash_annual_rate: float = 0.0, n_monkeys: int = 1000, seed: int = 0) -> dict` with keys `profit_pctile`, `dd_pctile`, `beats_90`, `avg_gross_candidate`, `avg_gross_monkeys`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_monkey.py — additions
import numpy as np
import pandas as pd
import pytest

from number7.strategies.clenow import ClenowMomentum, ClenowParams
from number7.strategies.sizing import SizingConfig
from number7.validation.monkey import monkey_test


def _clenow_panel(make_panel, n=600):
    """20 constituents with a clean momentum ordering, plus a rising SPY."""
    dates = pd.date_range("2020-01-01", periods=n, freq="B")
    data = {f"S{i:02d}": 100 * np.exp(0.0002 * i * np.arange(n)) for i in range(20)}
    data["SPY"] = 300 * np.exp(0.0004 * np.arange(n))
    close = pd.DataFrame(data, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False
    return make_panel(close, in_index=flags, high=close * 1.01, low=close * 0.99,
                      open_=close)


def test_monkeys_match_the_candidates_exposure_profile(make_panel):
    panel = _clenow_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)[40:]
    cfg = SizingConfig(sleeve_equity=50_000.0)
    cm = CostModel(min_half_spread_bps=0.0)
    cand = run_backtest(ClenowMomentum(ClenowParams()), panel, rb, cm,
                        sizing=cfg, initial=50_000.0)
    v = monkey_test(cand, panel, rb, cm,
                    null_factory=lambda s: ClenowMomentum(ClenowParams(), shuffle_seed=s),
                    sizing=cfg, initial=50_000.0, n_monkeys=25, seed=1)
    assert v["avg_gross_monkeys"] == pytest.approx(v["avg_gross_candidate"], abs=0.15)
    assert 0.0 <= v["profit_pctile"] <= 1.0
```

Keep `test_winner_beats_monkeys_and_null_does_not` as-is: with no `null_factory` the default
`RandomTopN` null is still correct for an always-invested candidate.

- [ ] **Step 2: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_monkey.py -v`
Expected: FAIL — `monkey_test()` got an unexpected keyword argument `null_factory`.

- [ ] **Step 3: Rewrite `monkey_test`**

```python
from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

from number7.engine.backtest import BacktestResult, run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, RandomTopN, Strategy
from number7.strategies.sizing import SizingConfig


def _avg_gross(res: BacktestResult) -> float:
    return float(res.weights.sum(axis=1).mean()) if len(res.weights) else 0.0


def monkey_test(candidate: BacktestResult, panel: PanelView,
                rebalance_dates: pd.DatetimeIndex, cost_model: CostModel, *,
                null_factory: Callable[[int], Strategy] | None = None,
                sizing: SizingConfig | None = None, initial: float = 1.0,
                cash_annual_rate: float = 0.0,
                n_monkeys: int = 1000, seed: int = 0) -> dict:
    """Davey's monkey test (KB-07): random systems matched on the candidate's breadth,
    identical schedule/sizing/costs (holding-period-preserving by construction — same
    weekly cadence, no IID shuffling). Production config uses n_monkeys=8000.

    `null_factory(seed) -> Strategy` supplies a MATCHED null. The default RandomTopN is
    always fully invested and equal-weight, which is a mismatched null for a part-cash,
    ATR-sized candidate — it measures cash exposure rather than ranking skill (spec §10.2).
    A Clenow run must pass `lambda s: ClenowMomentum(params, shuffle_seed=s)`, which
    randomizes only the RANKING and keeps the filters, regime gate, sizing and resolution
    identical, plus the same `sizing` config the candidate used."""
    held = (candidate.weights > 0).sum(axis=1)
    breadth = max(int(held.median()) if len(held) else 1, 1)
    factory = null_factory or (lambda s: RandomTopN(n=breadth, seed=s))
    cand = summary(candidate)
    profits, dds, gross = [], [], []
    for k in range(n_monkeys):
        res = run_backtest(factory(seed * 100_003 + k), panel, rebalance_dates, cost_model,
                           sizing=sizing, initial=initial,
                           cash_annual_rate=cash_annual_rate)
        s = summary(res)
        profits.append(s["cagr"])
        dds.append(s["max_dd"])
        gross.append(_avg_gross(res))
    profit_pctile = float(np.mean([cand["cagr"] > p for p in profits]))
    dd_pctile = float(np.mean([cand["max_dd"] >= d for d in dds]))   # higher = shallower
    return {"profit_pctile": profit_pctile, "dd_pctile": dd_pctile,
            "beats_90": profit_pctile >= 0.9 and dd_pctile >= 0.5,
            "avg_gross_candidate": _avg_gross(candidate),
            "avg_gross_monkeys": float(np.mean(gross)) if gross else 0.0}
```

- [ ] **Step 4: Run and commit**

Run: `set -o pipefail && uv run pytest tests/test_monkey.py -v && uv run ruff check src tests`
Expected: PASS, clean.

```bash
git add src/number7/validation/monkey.py tests/test_monkey.py
git commit -m "fix(validation): let the monkey null be matched to the candidate

RandomTopN is always fully invested and equal-weight, so against a part-cash, ATR-sized
candidate it measured cash exposure rather than ranking skill (spec §10.2, confirmed
defect #3). monkey_test now takes null_factory(seed) and the candidate's SizingConfig, so
a Clenow monkey randomizes only the ranking and passes through identical filters, regime
gate, sizing and resolution. Average gross exposure is reported for both sides so a
mismatch is visible rather than silent.

The default stays RandomTopN, which is the right null for an always-invested candidate."
```

---

### Task 10: Non-paper guard keyed on `risk_layer_version`

The portfolio risk layer (vol-target scalar, sector caps, loss brakes, liquidity overlay) is
deferred to its own spec. **Deferral is safe only under an enforced gate, and a configuration
flag is not that gate** (spec §3). Twenty-five positions each targeting a 10bp daily move imply
~8% annualized volatility if independent but **~23% at an average pairwise correlation of 0.30**
— ATR parity equalizes standalone dollar movement and does nothing about common equity risk.

Enforcing this on `Settings` itself means no live process can even construct its configuration,
which cannot be bypassed by a call site forgetting to call a guard function.

**Files:**
- Modify: `src/number7/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `Settings.trading_mode: Literal["paper", "live"] = "paper"`, `Settings.risk_layer_version: str | None = None`, and a `model_validator` refusing the combination.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py — additions
import pytest

from number7.config import Settings


def _base(tmp_path, **kw):
    return dict(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path, **kw)


def test_defaults_to_paper(tmp_path):
    assert Settings(**_base(tmp_path)).trading_mode == "paper"


def test_live_without_risk_layer_is_refused(tmp_path):
    with pytest.raises(ValueError, match="risk_layer_version"):
        Settings(**_base(tmp_path, trading_mode="live"))


def test_live_with_risk_layer_is_allowed(tmp_path):
    s = Settings(**_base(tmp_path, trading_mode="live", risk_layer_version="2026-09-a"))
    assert s.risk_layer_version == "2026-09-a"
```

- [ ] **Step 2: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_config.py -v`
Expected: FAIL — `Settings` has no `trading_mode`; `extra="ignore"` swallows it silently.

- [ ] **Step 3: Add the gate**

`src/number7/config.py`.

```python
from typing import Literal

from pydantic import model_validator


class Settings(BaseSettings):
    ...
    trading_mode: Literal["paper", "live"] = "paper"
    risk_layer_version: str | None = None

    @model_validator(mode="after")
    def _refuse_live_without_risk_layer(self) -> "Settings":
        """Blueprint §8 / spec §3: the portfolio risk layer is deferred, and deferral is
        only safe under an ENFORCED gate. 25 ATR-parity positions imply ~23% annualized
        vol at 0.30 average pairwise correlation, not the ~8% independence would give —
        ATR parity equalizes standalone dollar movement and does nothing about common
        equity risk. Enforced on Settings so no live process can even start; a call-site
        guard could be forgotten.

        Sequencing for capital (spec §3): build the production profile, estimate the
        Monte-Carlo drawdown thresholds, freeze them, RE-RUN the full gauntlet on the
        production profile, and only then set risk_layer_version."""
        if self.trading_mode != "paper" and self.risk_layer_version is None:
            raise ValueError(
                f"trading_mode={self.trading_mode!r} requires risk_layer_version to be set; "
                "the portfolio risk layer (vol target, sector caps, loss brakes, liquidity "
                "overlay) is not built yet, so non-paper trading is refused")
        return self
```

- [ ] **Step 4: Run and commit**

Run: `set -o pipefail && uv run pytest tests/test_config.py -v && uv run pytest 2>&1 | tail -5`
Expected: PASS.

```bash
git add src/number7/config.py tests/test_config.py
git commit -m "feat(config): refuse non-paper trading while the risk layer is unbuilt

The portfolio risk layer is deferred to its own spec, and that deferral is only safe under
an enforced gate - documentation is not sufficient (spec §3). 25 ATR-parity positions each
targeting a 10bp daily move imply ~23% annualized volatility at 0.30 average pairwise
correlation, not the ~8% independence would give; ATR parity does nothing about common
equity risk.

Enforced as a Settings validator so a live process cannot construct its configuration at
all. A call-site guard could be forgotten; this cannot."
```

---

### Task 11: Pre-registrations

Two **separate** registrations (spec §10): a one-point fidelity replication has no search, so
DSR is not meaningfully applicable at N=1, and blending it with a searched variant into one
registration spanning "a narrow range" is the weakest form of both. Diagnostics get a distinct
family so `Ledger.family_trials("clenow_momentum")` never counts them.

**Files:**
- Create: `src/number7/research/preregs.py`
- Test: `tests/test_preregs.py`

**Interfaces:**
- Consumes: `PreRegistration`, `Ledger.register`, `param_hash`.
- Produces: `CLENOW_REFERENCE`, `CLENOW_SEARCHED`, `CLENOW_DIAGNOSTIC` (all `PreRegistration`), `DIAGNOSTIC_FAMILY = "clenow_diagnostic"`, `CANDIDATE_FAMILY = "clenow_momentum"`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_preregs.py
import pytest

from number7.research.ledger import Ledger
from number7.research.preregs import (CANDIDATE_FAMILY, CLENOW_DIAGNOSTIC,
                                      CLENOW_REFERENCE, CLENOW_SEARCHED,
                                      DIAGNOSTIC_FAMILY)
from number7.validation.dsr import dsr_hurdle


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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `set -o pipefail && uv run pytest tests/test_preregs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'number7.research.preregs'`.

- [ ] **Step 3: Write the pre-registrations**

`src/number7/research/preregs.py`.

```python
from __future__ import annotations

from number7.research.registry import PreRegistration

CANDIDATE_FAMILY = "clenow_momentum"
DIAGNOSTIC_FAMILY = "clenow_diagnostic"

_CITATIONS = ["KB-02 Clenow, Stocks on the Move",
              "KB-08 Clenow, Trading Evolved",
              "KB-11 §9a", "blueprint §6", "spec 2026-07-23-clenow-momentum-sleeve-design"]

_MECHANISM = (
    "Cross-sectional equity momentum: over a 90-session window the OLS slope of log price "
    "against ordinal session index, annualized at 250 sessions and multiplied by R-squared "
    "as a smoothness penalty, ranks S&P 500 constituents. Positions are ATR-parity sized "
    "so each name targets the same daily dollar move, and a 200-day SMA regime gate on the "
    "index proxy blocks NEW entries while leaving retained names funded and re-sized. "
    "The economic claim is 12-month-scale price continuity net of noise; the R-squared "
    "term is a smoothness heuristic, not a significance test.")

CLENOW_REFERENCE = PreRegistration(
    family=CANDIDATE_FAMILY,
    origin="human",
    mechanism=_MECHANISM + (" REFERENCE PROFILE: the published parameters exactly, with "
                            "production overlays off. This is FIDELITY EVIDENCE, not an "
                            "alpha claim, and is never treated as deployable evidence."),
    citations=_CITATIONS,
    expected_effect=(
        "Reproduces the published system's qualitative behaviour on the 2005-2014 overlap: "
        "positive Sharpe, drawdown materially shallower than a fully-invested index through "
        "2008, and average gross exposure well below 1.0. A correct implementation may still "
        "underperform the book - window choice, cash treatment, fees, vendor differences and "
        "post-publication decay are all legitimate causes."),
    falsification=(
        "Regime-off episodes do not precede index drawdowns more often than chance across "
        "2004-present; or the paired regime-gate ablation shows no exposure-adjusted "
        "improvement; or the full system fails to beat its own no-R2 / no-gap / equal-weight "
        "ablations; or DSR falls below the 0.98 hurdle. Any of these is a documented KILL."),
    param_space={"lookback": [90], "atr_window": [20], "ma_filter": [100],
                 "regime_ma": [200], "gap_threshold": [0.15], "risk_factor": [0.001],
                 "hold_top_pct": [0.20], "max_positions": [30], "drift_band": [0.05]},
)

CLENOW_SEARCHED = PreRegistration(
    family=CANDIDATE_FAMILY,
    origin="human",
    mechanism=_MECHANISM + (" SEARCHED VARIANT: the declared neighbourhood of the published "
                            "parameters. Registered separately from the reference point "
                            "because a one-point replication has no search, so DSR is not "
                            "meaningfully applicable at N=1."),
    citations=_CITATIONS,
    expected_effect=(
        "Performance is a smooth, broad plateau in the parameter neighbourhood rather than a "
        "spike at the published point. A sharp optimum would itself be evidence of fitting."),
    falsification=(
        "The published point is a lone spike surrounded by materially worse neighbours; or "
        "the best cell fails the 0.98 DSR hurdle once the full declared space is counted; or "
        "walk-forward efficiency falls below the 0.5 floor."),
    param_space={"lookback": [60, 90, 120], "atr_window": [14, 20], "ma_filter": [100],
                 "regime_ma": [200], "gap_threshold": [0.15], "risk_factor": [0.001],
                 "hold_top_pct": [0.20], "max_positions": [20, 30], "drift_band": [0.05]},
)

CLENOW_DIAGNOSTIC = PreRegistration(
    family=DIAGNOSTIC_FAMILY,
    origin="human",
    mechanism=_MECHANISM + (" DIAGNOSTICS ONLY: ablations, the reference/deployable profile "
                            "pair, cash-rate and cost-sensitivity runs. None is a deployment "
                            "candidate, so none counts toward the DSR trial budget - which is "
                            "why they live in a separate ledger family (spec §10)."),
    citations=_CITATIONS,
    expected_effect=("Each ablation degrades the full system: removing R-squared, the regime "
                     "gate, the gap filter, or ATR parity should each cost exposure-adjusted "
                     "return. If the full system cannot beat its own ablations the "
                     "implementation is suspect; if it crushes them, that is also signal."),
    falsification=("An ablation matches or beats the full system, indicating a component is "
                   "inert or actively harmful as implemented."),
    param_space={"ablation": ["none", "no_r2", "no_regime", "no_gap", "equal_weight"],
                 "cost_multiple": [0.0, 1.0, 2.0],
                 "cash_annual_rate": [0.0, 0.02, 0.04],
                 "profile": ["reference", "deployable"]},
)
```

- [ ] **Step 4: Run and commit**

Run: `set -o pipefail && uv run pytest tests/test_preregs.py -v`
Expected: PASS.

```bash
git add src/number7/research/preregs.py tests/test_preregs.py
git commit -m "feat(research): pre-register the Clenow reference and searched variant

Two separate registrations, not one spanning a narrow range: a one-point fidelity
replication has no search, so DSR is not meaningfully applicable at N=1 and blending it
with a searched grid is the weakest form of both (spec §10).

Diagnostics - ablations, the profile pair, cost and cash-rate sensitivity - register under
a distinct ledger family so family_trials() for the candidate never counts them, which is
the accounting the spec settles BEFORE the first run rather than after.

Pinned constants (ann_factor, ATR smoothing and burn-in, drift-band mode) are absent from
both searched spaces: commingling them with real hyperparameters would misrepresent the
degrees of freedom used for DSR scaling."
```

---

### Task 12: Calibration runner and memo

The gates in spec §11.2 replace an earlier version with almost no discriminating power:
"max drawdown materially shallower than SPY's −55%" is passed by *any* system holding
meaningful cash, including one that is 50% cash by accident or has a broken fill loop.

**Files:**
- Create: `src/number7/research/calibrate_clenow.py`
- Create: `docs/research/2026-08-clenow-calibration-memo.md` (written by the runner, then edited by hand)
- Test: `tests/test_calibrate_clenow.py`

**Interfaces:**
- Consumes: `build_panel`, `weekly_rebalances`, `run_backtest`, `summary`, `CostModel`, `SizingConfig`, `ClenowMomentum`, `ClenowParams`, `walk_forward`, `WFProtocol`, `monkey_test`, `block_bootstrap_dd`, `psr`/`dsr`/`dsr_hurdle`, `EqualWeightIndex`, `gate6`, `Ledger`, the three pre-registrations.
- Produces:
  - `PROFILES: dict[str, tuple[ClenowParams, SizingConfig]]` — `"reference"` and `"deployable"`, both frozen
  - `regime_episodes(panel, params) -> list[dict]`
  - `exposure_metrics(result, panel) -> dict`
  - `turnover_at_transitions(result, episodes) -> dict`
  - `run_profile(panel, params, sizing, cost_model, *, cash_annual_rate=0.0, initial=50_000.0) -> BacktestResult`
  - `main() -> None` (entry point: `uv run python -m number7.research.calibrate_clenow`)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_calibrate_clenow.py
import numpy as np
import pandas as pd
import pytest

from number7.engine.costs import CostModel
from number7.research.calibrate_clenow import (PROFILES, exposure_metrics,
                                               regime_episodes, run_profile,
                                               turnover_at_transitions)
from number7.strategies.clenow import ClenowParams


def _regime_panel(make_panel, n=700):
    """SPY rises, falls below its SMA200, then recovers — two regime-off episodes."""
    dates = pd.date_range("2019-01-01", periods=n, freq="B")
    spy = np.concatenate([300 * np.exp(0.0008 * np.arange(300)),
                          300 * np.exp(0.0008 * 299) * np.exp(-0.0025 * np.arange(150)),
                          300 * np.exp(0.0008 * 299) * np.exp(-0.0025 * 149)
                          * np.exp(0.0012 * np.arange(n - 450))])
    data = {f"S{i:02d}": 100 * np.exp(0.0003 * (i + 1) * np.arange(n)) for i in range(12)}
    data["SPY"] = spy
    close = pd.DataFrame(data, index=dates)
    flags = pd.DataFrame(True, index=dates, columns=close.columns)
    flags.loc[:, "SPY"] = False
    return make_panel(close, in_index=flags, high=close * 1.01, low=close * 0.99,
                      open_=close)


def test_both_profiles_are_frozen_and_distinct():
    assert set(PROFILES) == {"reference", "deployable"}
    ref_p, ref_s = PROFILES["reference"]
    dep_p, dep_s = PROFILES["deployable"]
    assert (ref_p, ref_s) != (dep_p, dep_s)
    assert dep_s.position_cap == 0.10 and dep_s.min_position_dollars == 1000.0


def test_regime_episodes_are_scored_over_the_whole_history(make_panel):
    panel = _regime_panel(make_panel)
    eps = regime_episodes(panel, ClenowParams())
    assert len(eps) >= 1
    e = eps[0]
    assert set(e) == {"start", "end", "sessions", "index_return_through_episode",
                      "post_episode_return", "hit"}
    assert e["hit"] is (e["index_return_through_episode"] < 0)


def test_exposure_metrics_report_average_gross_as_first_class(make_panel):
    panel = _regime_panel(make_panel)
    params, sizing = PROFILES["deployable"]
    res = run_profile(panel, params, sizing, CostModel(min_half_spread_bps=0.0))
    m = exposure_metrics(res, panel)
    assert 0.0 < m["avg_gross"] <= 1.0
    assert set(m) >= {"avg_gross", "return_per_unit_exposure", "beta_vs_index", "sharpe"}


def test_turnover_at_transitions_is_reported_separately(make_panel):
    panel = _regime_panel(make_panel)
    params, sizing = PROFILES["deployable"]
    res = run_profile(panel, params, sizing, CostModel(min_half_spread_bps=0.0))
    t = turnover_at_transitions(res, regime_episodes(panel, params))
    assert set(t) == {"avg_turnover", "avg_turnover_at_transitions", "n_transitions"}


def test_deployable_profile_never_breaches_its_own_limits(make_panel):
    """Contract-wide (spec §12): every resolved book on a real run passes validate_book."""
    from number7.strategies.sizing import validate_book
    panel = _regime_panel(make_panel)
    params, sizing = PROFILES["deployable"]
    res = run_profile(panel, params, sizing, CostModel(min_half_spread_bps=0.0))
    for t in res.rebalance_dates:
        validate_book(res.weights.loc[t], sizing)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `set -o pipefail && uv run pytest tests/test_calibrate_clenow.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'number7.research.calibrate_clenow'`.

- [ ] **Step 3: Write the profiles and metric helpers**

`src/number7/research/calibrate_clenow.py`.

```python
"""Clenow calibration runner (spec §11). Run:

    uv run python -m number7.research.calibrate_clenow

Writes docs/research/2026-08-clenow-calibration-memo.md and logs every run to the trials
ledger. Diagnostics register under DIAGNOSTIC_FAMILY so they never inflate the candidate's
DSR trial count.

ANTI-FITTING CLAUSE (spec §11.4): "a discrepancy triggers investigation, not failure" is
bounded. Legitimate: implementation bug found -> fix -> re-run. NOT legitimate: parameter
nudged until the chart matches the book. Any parameter change spawns a NEW pre-registration
and counts as a new trial."""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from number7.benchmarks.ew import EqualWeightIndex, gate6
from number7.config import get_settings
from number7.data.snapshot import current_snapshot
from number7.engine.backtest import BacktestResult, run_backtest, summary
from number7.engine.costs import CostModel
from number7.engine.live import build_panel
from number7.engine.schedule import weekly_rebalances
from number7.research.ledger import Ledger
from number7.research.preregs import (CANDIDATE_FAMILY, CLENOW_DIAGNOSTIC,
                                      CLENOW_REFERENCE)
from number7.strategies.clenow import ClenowMomentum, ClenowParams
from number7.strategies.sizing import SizingConfig
from number7.validation.dsr import dsr, dsr_hurdle
from number7.validation.monkey import monkey_test
from number7.validation.montecarlo import block_bootstrap_dd
from number7.validation.walkforward import WFProtocol, walk_forward

SLEEVE_EQUITY = 50_000.0
CASH_ANNUAL_RATE = 0.0          # PINNED for primary runs (spec §11.3). We have no bill
# series in the snapshot, so a historical rate path would be fabricated. The 2%/4%
# diagnostics below quantify the handicap instead; the memo must state all three.
CASH_DIAGNOSTICS = (0.02, 0.04)
COST_MULTIPLES = (0.0, 1.0, 2.0)
MEMO = Path("docs/research/2026-08-clenow-calibration-memo.md")

# Two FROZEN profiles (spec §4), not a runtime toggle. The configuration that passes the
# gauntlet must be the configuration that ships, so both are gauntlet-run - but the
# reference profile is fidelity evidence only and is NEVER deployable evidence.
PROFILES: dict[str, tuple[ClenowParams, SizingConfig]] = {
    "reference": (
        ClenowParams(),
        SizingConfig(sleeve_equity=SLEEVE_EQUITY, position_cap=1.0,
                     min_position_dollars=0.0, gross_max=1.0, drift_band=0.0,
                     max_positions=100, forced_resize_periods=10**6),
    ),
    "deployable": (
        ClenowParams(),
        SizingConfig(sleeve_equity=SLEEVE_EQUITY, position_cap=0.10,
                     min_position_dollars=1000.0, gross_max=1.0, drift_band=0.05,
                     max_positions=30, forced_resize_periods=8),
    ),
}

ABLATIONS: dict[str, ClenowParams] = {
    "no_r2": ClenowParams(use_r2=False),
    "no_regime": ClenowParams(use_regime=False),
    "no_gap": ClenowParams(use_gap_filter=False),
    "equal_weight": ClenowParams(equal_weight=True),
}


def run_profile(panel, params: ClenowParams, sizing: SizingConfig, cost_model: CostModel,
                *, cash_annual_rate: float = CASH_ANNUAL_RATE,
                initial: float = SLEEVE_EQUITY) -> BacktestResult:
    rb = weekly_rebalances(panel.sessions)
    return run_backtest(ClenowMomentum(params), panel, rb, cost_model, sizing=sizing,
                        initial=initial, cash_annual_rate=cash_annual_rate)


def regime_episodes(panel, params: ClenowParams) -> list[dict]:
    """Every regime-off episode over the whole history, scored on hit rate and cost
    (spec §11.2.2). Resting a gate on N=1 realization of the event it exists to handle is
    not a gate."""
    spy = panel.px_close[params.regime_symbol]
    sma = spy.rolling(params.regime_ma).mean()
    off = (spy <= sma) & sma.notna()
    episodes: list[dict] = []
    idx = panel.sessions
    grp = (off != off.shift()).cumsum()
    tr = panel.tr_close[params.regime_symbol]
    for _, block in off.groupby(grp):
        if not bool(block.iloc[0]) or len(block) < 2:
            continue
        start, end = block.index[0], block.index[-1]
        fwd = idx[idx > end]
        horizon = fwd[:63]          # ~3 months forward, or what remains
        after = (float(tr.loc[horizon[-1]] / tr.loc[end] - 1.0)
                 if len(horizon) else float("nan"))
        during = float(tr.loc[end] / tr.loc[start] - 1.0)
        episodes.append({"start": str(start.date()), "end": str(end.date()),
                         "sessions": int(len(block)),
                         "index_return_through_episode": during,
                         "post_episode_return": after,          # ~3 months after re-entry
                         "hit": bool(during < 0)})
    return episodes
```

`hit` is scored on the return **through** the episode, because the question the gate answers
is "did the off-state coincide with a decline it kept us out of". `post_episode_return` is
reported alongside so the memo can see whipsaw cost — an episode that ends right before a
sharp rally is a false positive even when its own span was negative.

- [ ] **Step 4: Write the exposure and turnover metrics**

```python
def exposure_metrics(result: BacktestResult, panel) -> dict:
    """Under-investment is EXPECTED (spec §8.2), so raw CAGR against a fully-invested SPY
    through a long bull punishes the design for working as intended. Gate on Sharpe, beta,
    and return per unit of average gross exposure, and report average gross exposure as a
    first-class metric (spec §11.2.3)."""
    s = summary(result)
    gross = result.weights.sum(axis=1)
    avg_gross = float(gross.mean()) if len(gross) else 0.0
    eq = result.equity.dropna()
    r = np.log(eq).diff().dropna()
    bench = np.log(panel.tr_close["SPY"]).diff().reindex(r.index).fillna(0.0)
    var_b = float(bench.var(ddof=0))
    beta = float(np.cov(r, bench, ddof=0)[0, 1] / var_b) if var_b > 0 else float("nan")
    return {"avg_gross": avg_gross,
            "return_per_unit_exposure": s["cagr"] / avg_gross if avg_gross > 0 else 0.0,
            "beta_vs_index": beta,
            "sharpe": s["sharpe"],
            "cagr": s["cagr"],
            "max_dd": s["max_dd"],
            "delisting_exits": int(result.delisting_exits.sum())}


def turnover_at_transitions(result: BacktestResult, episodes: list[dict]) -> dict:
    """Whipsaw-driven turnover spikes at SMA crossings are the known failure mode, and an
    average hides them (spec §11.2.4)."""
    marks = pd.DatetimeIndex(sorted({pd.Timestamp(e[k]) for e in episodes
                                     for k in ("start", "end")}))
    t = result.turnover
    if not len(t):
        return {"avg_turnover": 0.0, "avg_turnover_at_transitions": 0.0, "n_transitions": 0}
    near = t.index[[bool((abs(marks - d) <= pd.Timedelta(days=7)).any()) for d in t.index]]
    return {"avg_turnover": float(t.mean()),
            "avg_turnover_at_transitions": float(t.loc[near].mean()) if len(near) else 0.0,
            "n_transitions": int(len(near))}
```

- [ ] **Step 5: Run the metric tests**

Run: `set -o pipefail && uv run pytest tests/test_calibrate_clenow.py -v`
Expected: PASS.

- [ ] **Step 6: Write the runner and memo writer**

```python
def _code_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                          text=True, check=True).stdout.strip()


def _gauntlet(panel, params, sizing, cost_model, res, label: str) -> dict:
    """Gates 2-6 for one profile. Both frozen profiles get the full run; only the
    deployable one is ever treated as deployable evidence (spec §4)."""
    rb = weekly_rebalances(panel.sessions)
    eq = res.equity.dropna()
    r = np.log(eq).diff().dropna()
    wf = walk_forward(lambda: ClenowMomentum(params), panel,
                      WFProtocol(), cost_model, sizing=sizing, initial=SLEEVE_EQUITY)
    mk = monkey_test(res, panel, rb, cost_model,
                     null_factory=lambda s: ClenowMomentum(params, shuffle_seed=s),
                     sizing=sizing, initial=SLEEVE_EQUITY, n_monkeys=1000, seed=17)
    bench = run_backtest(EqualWeightIndex(), panel, rb, cost_model, initial=SLEEVE_EQUITY)
    return {
        "label": label,
        "summary": summary(res),
        "exposure": exposure_metrics(res, panel),
        "walk_forward": {"wfe": wf.wfe, "n_windows": len(wf.windows),
                         "passes": wf.passes(WFProtocol())},
        "monkey": mk,
        "bootstrap": block_bootstrap_dd(r.to_numpy(), block=10, n=2000, seed=17),
        "gate6": gate6(summary(res), summary(bench)),
        "sharpe_per_period": float(r.mean() / r.std(ddof=0)) if r.std(ddof=0) > 0 else 0.0,
        "n_obs": int(len(r)),
        "skew": float(r.skew()), "kurt": float(r.kurt() + 3.0),
    }


def main() -> None:
    settings = get_settings()
    root = current_snapshot(settings)
    if root is None:
        raise SystemExit("no promoted snapshot: run number7.ops.nightly first")
    panel = build_panel(root)
    cost_model = CostModel()
    led = Ledger(settings.data_dir / "trials.duckdb")
    sha, snap = _code_sha(), root.name

    # CLENOW_SEARCHED is NOT registered here: this run searches nothing. Declaring a grid
    # we do not walk would misreport the degrees of freedom in exactly the direction the
    # ledger exists to prevent. The follow-on grid run registers it.
    reg_ref = led.register(CLENOW_REFERENCE)
    reg_diag = led.register(CLENOW_DIAGNOSTIC)

    report: dict = {"snapshot": snap, "code_sha": sha,
                    "cash_annual_rate": CASH_ANNUAL_RATE, "profiles": {}, "diagnostics": {}}

    for name, (params, sizing) in PROFILES.items():
        res = run_profile(panel, params, sizing, cost_model)
        g = _gauntlet(panel, params, sizing, cost_model, res, name)
        n_trials = led.family_trials(CANDIDATE_FAMILY)
        g["dsr"] = dsr(g["sharpe_per_period"], g["n_obs"], g["skew"], g["kurt"],
                       n_trials=n_trials,
                       var_trials=led.var_of_trial_sharpes(CANDIDATE_FAMILY))
        g["dsr_hurdle"] = dsr_hurdle(n_trials, CLENOW_REFERENCE.origin)
        g["dsr_passes"] = g["dsr"] >= g["dsr_hurdle"]
        # The reference profile IS the registered candidate — the one-point replication.
        # The PROFILE PAIR is a declared diagnostic (spec §10): neither profile is a
        # deployment candidate today, and the deployable profile gets its own full
        # gauntlet re-run before capital, after the risk layer exists.
        reg = reg_ref if name == "reference" else reg_diag
        led.log_run(reg, sha, snap, {"profile": name, **asdict(params)},
                    {**g["summary"], **g["exposure"], "dsr": g["dsr"]})
        report["profiles"][name] = g

    report["regime_episodes"] = regime_episodes(panel, PROFILES["deployable"][0])
    dep_params, dep_sizing = PROFILES["deployable"]
    dep_res = run_profile(panel, dep_params, dep_sizing, cost_model)
    report["turnover"] = turnover_at_transitions(dep_res, report["regime_episodes"])

    # --- diagnostics: excluded from the DSR trial count by construction (own family) ---
    for name, params in ABLATIONS.items():
        res = run_profile(panel, params, dep_sizing, cost_model)
        m = exposure_metrics(res, panel)
        led.log_run(reg_diag, sha, snap, {"ablation": name}, {**summary(res), **m})
        report["diagnostics"][f"ablation_{name}"] = m
    for mult in COST_MULTIPLES:
        cm = CostModel(commission_bps=CostModel().commission_bps * mult,
                       min_half_spread_bps=CostModel().min_half_spread_bps * mult)
        res = run_profile(panel, dep_params, dep_sizing, cm)
        m = exposure_metrics(res, panel)
        led.log_run(reg_diag, sha, snap, {"cost_multiple": mult}, {**summary(res), **m})
        report["diagnostics"][f"cost_x{mult}"] = m
    for rate in CASH_DIAGNOSTICS:
        res = run_profile(panel, dep_params, dep_sizing, cost_model, cash_annual_rate=rate)
        m = exposure_metrics(res, panel)
        led.log_run(reg_diag, sha, snap, {"cash_annual_rate": rate}, {**summary(res), **m})
        report["diagnostics"][f"cash_{rate}"] = m

    MEMO.parent.mkdir(parents=True, exist_ok=True)
    MEMO.write_text(_memo(report))
    print(json.dumps({k: v for k, v in report.items() if k != "regime_episodes"},
                     indent=2, default=str))


def _memo(r: dict) -> str:
    ep = r["regime_episodes"]
    hits = sum(1 for e in ep if e["hit"])
    rows = "\n".join(f"| {e['start']} | {e['end']} | {e['sessions']} | "
                     f"{e['index_return_through_episode']:+.2%} | "
                     f"{e['post_episode_return']:+.2%} | {'yes' if e['hit'] else 'no'} |"
                     for e in ep)
    prof = "\n".join(
        f"| {name} | {g['summary']['cagr']:.2%} | {g['summary']['sharpe']:.2f} | "
        f"{g['summary']['max_dd']:.2%} | {g['exposure']['avg_gross']:.2f} | "
        f"{g['exposure']['return_per_unit_exposure']:.2%} | {g['exposure']['beta_vs_index']:.2f} | "
        f"{g['walk_forward']['wfe']:.2f} | {g['monkey']['profit_pctile']:.2f} | "
        f"{g['dsr']:.3f} vs {g['dsr_hurdle']:.2f} |"
        for name, g in r["profiles"].items())
    diag = "\n".join(f"| {k} | {v['cagr']:.2%} | {v['sharpe']:.2f} | {v['max_dd']:.2%} | "
                     f"{v['avg_gross']:.2f} | {v['return_per_unit_exposure']:.2%} |"
                     for k, v in r["diagnostics"].items())
    return f"""# Clenow Momentum — Calibration Memo

**Snapshot:** `{r['snapshot']}` · **Code:** `{r['code_sha']}` · **Cash rate:** {r['cash_annual_rate']:.2%}

Generated by `number7.research.calibrate_clenow`. Numbers are machine-written; the
interpretation sections below are written by hand and are the point of the document.

## Window

Published results span roughly 1999–2014; our history starts 2004. The overlap
(2005–2014, after warm-up) is the quantitative comparison; 2015→present is
post-publication validation. **The missing 2000–2003 window removes the dot-com bear** —
arguably the episode that best justifies a 200-day regime filter — leaving 2008 as the only
severe bear in sample.

## Profiles

The reference profile is **fidelity evidence only and is never deployable evidence.**

| profile | CAGR | Sharpe | max DD | avg gross | return / unit exposure | beta | WFE | monkey pctile | DSR |
|---|---|---|---|---|---|---|---|---|---|
{prof}

## Regime-off episodes ({hits}/{len(ep)} preceded a negative index move)

| start | end | sessions | index return through episode | ~3m after re-entry | hit |
|---|---|---|---|---|---|
{rows}

## Turnover

- average: {r['turnover']['avg_turnover']:.2%}
- **at regime transitions:** {r['turnover']['avg_turnover_at_transitions']:.2%} over
  {r['turnover']['n_transitions']} rebalances — whipsaw spikes are the known SMA-crossing
  failure mode and an average hides them.

## Diagnostics (excluded from the DSR trial count)

| run | CAGR | Sharpe | max DD | avg gross | return / unit exposure |
|---|---|---|---|---|---|
{diag}

## Declared platform adaptations

- **Cadence:** the published system maintains the roster weekly but re-sizes every second
  Wednesday; we rebalance weekly (Tuesday default) with MOC fills. Turnover differences
  trace to this, not to a bug.
- **Cash rate:** primary runs earn {r['cash_annual_rate']:.2%} on cash. The 2%/4%
  diagnostics above bound the handicap; the blueprint routes idle cash to a T-bill sleeve,
  which this engine does not yet model.
- **Regime proxy:** capital-adjusted SPY. `$SPX` from Norgate's US Indices database is a
  registered VARIANT, not a free swap.
- **Gap definition:** overnight (`|open / prev_close − 1|`). Norgate defines the open as the
  first print from any venue while the close is generally the listing-exchange auction, so
  vendor-specific outliers are possible.

## To be written by hand

1. Does the overlap-window comparison support fidelity? Name the specific discrepancies.
2. Paired regime-gate ablation: is (gated − ungated) positive on exposure-adjusted terms?
3. Do the ablations behave as expected, and does anything beat the full system?
4. **Delisting:** state whether the Norgate total-return series embeds a terminal delisting
   return. If it does not, the backtest overstates. Event count this run:
   see `delisting_exits` in the profile table source.
5. **Index membership:** confirm from Norgate documentation that membership intervals are
   EFFECTIVE dates, not announcement dates. Announcement dates would make the book trade
   the S&P-addition pop — a real look-ahead. Deletion-date exits are the classic
   worst-execution point and are a recorded known cost.
6. Verdict: proceed to paper, or documented kill.
"""


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run the offline tests and lint**

Run: `set -o pipefail && uv run pytest 2>&1 | tail -20 && uv run ruff check src tests`
Expected: PASS, clean. The full suite should now be ~120 tests.

- [ ] **Step 8: Commit**

```bash
git add src/number7/research/calibrate_clenow.py tests/test_calibrate_clenow.py
git commit -m "feat(research): add the Clenow calibration runner and memo writer

Implements the spec §11.2 gates, which replace a version with almost no discriminating
power: 'max drawdown materially shallower than SPY' is passed by any system holding
meaningful cash. In its place - a paired regime-gate ablation, every regime-off episode
scored rather than one, exposure-adjusted return with average gross exposure as a
first-class metric, turnover measured AT regime transitions specifically, 0x/1x/2x cost
sensitivity, and the four ablations.

Both frozen profiles get the full gauntlet; the reference profile is fidelity evidence and
is never deployable evidence. Diagnostics log under the diagnostic family so they never
inflate the candidate's DSR trial count."
```

- [ ] **Step 9: Manual gate — run calibration on the promoted snapshot**

```bash
set -o pipefail && uv run python -m number7.research.calibrate_clenow 2>&1 | tail -60
```

Expected: `docs/research/2026-08-clenow-calibration-memo.md` written; the ledger contains
exactly two candidate-family runs (reference + deployable) and all diagnostics under
`clenow_diagnostic`. Verify:

```bash
uv run python -c "
from number7.config import get_settings
from number7.research.ledger import Ledger
led = Ledger(get_settings().data_dir / 'trials.duckdb')
print('candidate trials:', led.family_trials('clenow_momentum'))
print('diagnostic trials:', led.family_trials('clenow_diagnostic'))
"
```

Expected: candidate trials reflects only the two declared spaces (1 + the searched grid
size), diagnostics counted separately.

- [ ] **Step 10: Manual gate — write the memo's interpretation sections**

Fill sections 1–6 of "To be written by hand". Sections 4 and 5 require checking Norgate
documentation and cannot be answered from the offline suite — if the answer is unknown,
write "unknown" plus the check that would settle it, rather than an assumption.

- [ ] **Step 11: Commit the memo**

```bash
git add docs/research/2026-08-clenow-calibration-memo.md
git commit -m "docs(research): Clenow calibration memo

Overlap-window comparison, paired regime ablation, all regime-off episodes, exposure-adjusted
metrics, cost sensitivity, the pinned cash rate and the declared cadence deviation."
```

---

## Coverage against the spec

| Spec section | Where it lands |
|---|---|
| §2 dual-basis snapshot, schema, metadata | Task 1 |
| §3 in-scope list | Tasks 1–12 |
| §3 deferral gate (`risk_layer_version`) | Task 10 |
| §4 two frozen profiles | Task 12 `PROFILES` |
| §5.2 `Slate`, stateless strategy | Tasks 3, 8 |
| §5.3 `state_at_signal` vs `state_at_fill` | Task 5 |
| §5.4 module layout | Tasks 4, 8 |
| §6.1 ranking, ann_factor, ties, R² guard | Task 8 |
| §6.2 candidate set, rank-then-filter, gap | Tasks 2 (defect #1), 8 |
| §6.3 NaN contract, regime warm-up | Task 8 |
| §6.4 regime gate semantics | Task 8 |
| §6.5 Wilder ATR, absolute weights | Task 8 |
| §6.6 parameter space, pinned constants | Task 11 |
| §7 `PanelView` extension | Task 2 |
| §8.1–8.3 `SizingConfig`, resolver, band | Task 4 |
| §8.4 live-path holdings | Tasks 4 (`holdings_from_shares`), 5 |
| §9 engine changes, parity | Tasks 3, 5 |
| §10.1 walk-forward fold state | Task 6 |
| §10.2 monkey matching | Task 9 |
| §10.3 closed-loop causality | Task 7 |
| §10 DSR 0.98, ledger accounting | Task 11 |
| §11.1–11.5 calibration | Task 12 |
| §12 test plan | Tasks 1–12 (each test named in the spec appears in a task) |
| §13 deliverables | all tasks |
| §14 success criteria | verification checklist below |
| §15 `RandomTopN` RNG ticket | **not this plan** — but `ClenowMomentum(shuffle_seed=)` uses the correct `(seed, date)` construction so the new null does not inherit the bug |

## Final verification checklist (spec §14)

Run before declaring the plan complete. Evidence, not assertions.

- [ ] `set -o pipefail && uv run pytest` — all green, and the count is stated
- [ ] `uv run ruff check src tests` — clean
- [ ] `uv run pytest -m vm` — live Norgate audit green
- [ ] A promoted snapshot exists whose `meta.json` lists both bases, and `build_panel`
      raises `MissingBasisError` on a snapshot lacking the price basis
- [ ] `causality_violations` and `closed_loop_violations` both empty for `ClenowMomentum`;
      the leaky variant and `LookaheadTrap` both caught; cross-snapshot stability test green
- [ ] Golden-replay parity green **through resolution and the drift band**
- [ ] Ledger shows the pre-registrations preceding every run, and diagnostics in their own family
- [ ] Calibration memo written, including the hand-written interpretation sections
- [ ] `Settings(trading_mode="live")` raises without `risk_layer_version`

## Parked — deliberately not in this plan

- **Risk constitution §8 tuning.** Blueprint says draft numbers should be tuned before
  Phase 2. Outstanding, owner Viktor. Does not block this plan; does block real capital.
- **Paper probe accumulation.** `com.number7.paper` still buys 1 SPY every trading day into
  the paper account. Its gate purpose is served; unload it and flatten the position before
  Phase-2 reconciliation, or it will muddy live-vs-sim.
- **`RandomTopN` RNG is call-count dependent** (spec §15). Ticket, not this plan.
- **Portfolio risk layer** — vol-target scalar, sector caps, loss brakes, liquidity overlay.
  Its own spec. The hard guard in Task 10 is what makes the deferral safe.
- **Order service, broker reconciliation, ETF trend sleeve, RSI(2)** — separate sub-projects.

