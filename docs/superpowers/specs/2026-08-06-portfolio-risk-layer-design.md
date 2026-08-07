# Portfolio Risk Layer — Design Spec

**Date:** 2026-08-06
**Status:** approved design, pre-implementation
**Blueprint:** §8 (risk constitution), §6 (gauntlet)
**Predecessor:** `docs/superpowers/specs/2026-07-23-clenow-momentum-sleeve-design.md` §3
("Deferred to the portfolio risk-layer spec")
**Motivating evidence:** `docs/research/2026-08-clenow-calibration-memo.md` — the monkey
drawdown failure

## 1. Purpose

The Clenow calibration measured, empirically, the risk this layer exists to control: the
deployable profile out-earned every one of 1,000 rank-shuffled matched nulls (profit
percentile 1.000) while drawing down deeper than 99.9% of them (drawdown percentile 0.001).
Momentum ranking concentrates the book into names that fall together. ATR parity equalizes
standalone dollar movement and does nothing about common-factor risk: 25 positions at 10bp
each imply ~8% annualized vol if independent, ~23% at 0.30 average pairwise correlation.

This spec adds the deterministic per-rebalance overlay that closes that gap: a portfolio
volatility-target scalar with an anti-procyclicality clause, the §8 sector and top-3
concentration caps, and the liquidity overlay (ADV cap, Corwin–Schultz spread gate, beta
band). It is stage 2 and part of stage 3 of the §8 four-stage sizing pipeline.

## 2. Scope

### In scope

- `risk/` package: covariance estimation, Corwin–Schultz spread estimation, and the
  `RiskContext` overlay.
- `resolve_book` extension: one optional `risk: RiskContext | None` argument; the overlay
  stages inserted at normative positions in the resolution pipeline (§6).
- `PanelView.gics_sector` threaded from snapshot metadata.
- New durable state: the ratchet scalar `k_prev`, recorded by the engine and pinned by
  golden replay.
- One pre-registered overlay-on vs overlay-off ablation on the deployable profile.

### Out of scope, and where it goes

| deferred item | destination | why |
|---|---|---|
| Performance de-risking brakes (drawdown-rate halving, MC-99th full stop) | brakes spec, next | thresholds derive from a gauntlet run of a book that has THIS overlay in it; cannot precede it |
| Malfunction halts (4×-daily-vol day, live-vs-sim divergence, reconciliation mismatch) | order-service spec | requires broker truth that does not exist yet |
| Data/ops severity ladder | order-service spec | same |
| Correlation-breakdown brake (§8 "sustained spike ⇒ scalar tightens") | brakes spec | it is a brake; this layer only *records* `avg_corr` every rebalance so the brakes spec has a series to define "sustained spike" against |
| Setting `risk_layer_version` | Viktor, after the production-profile gauntlet re-run | the config guard's sequencing clause (`config.py`) |

Shipping this spec does NOT clear the trading gate. The sequencing for capital is
unchanged: build production profile → estimate MC thresholds → freeze → re-run the full
gauntlet on the production profile → only then set `risk_layer_version`.

## 3. Decisions resolved during design

| question | decision |
|---|---|
| Spec scope | Overlay only; brakes and halts split out (§2 table) |
| Point-in-time GICS | **Declared approximation:** the snapshot's current `gics_sector` labels the whole history. Known look-ahead, bounded impact (sector labels are near-static; the 2018 Communication Services restructure is the one big reshuffle, mislabeling GOOGL/META/DIS-class names pre-2018). Each immutable snapshot records the map as of its `db_date`, so a genuine PIT series accrues from 2026 forward. The bridge has no historical-classification endpoint; whether Norgate stores PIT GICS is unknown and NOT investigated — revisit only if the ablation shows the sector cap driving results |
| Portfolio vol estimator | **Ex-ante covariance:** EWMA of daily capital-basis log returns, shrunk toward a constant-correlation target. Sees concentration the same rebalance the strategy creates it; yields `avg_corr` for free |
| Anti-procyclicality mechanic | **Rate-limited ratchet:** down moves immediate and in full; up moves capped at `up_step` per rebalance. State is one float, `k_prev` |
| Parameters | **All frozen a priori.** Zero searched dimensions, zero trials consumed, no DSR interaction. One on/off ablation, report-only. Any later change is a declared constitution amendment with Viktor's sign-off — never a tuning loop |
| Beta band breach | **Monitor + page only.** Long-only, the only lever is exposure, and the vol scalar already pulls it — an automatic beta action would de-risk twice for one cause. Page after 4 consecutive out-of-band rebalances; never a sizing input |
| Architecture | **`RiskContext` computed before the resolver** (option C): all panel reads in one function, resolver stays a pure function of plain data |

## 4. Architecture

### 4.1 Modules

| module | job | depends on |
|---|---|---|
| `risk/covariance.py` | EWMA covariance + constant-correlation shrinkage; returns Σ and average pairwise correlation | numpy/pandas |
| `risk/spread.py` | Corwin–Schultz spread estimate from `px_high`/`px_low`; rolling median comparison | numpy/pandas |
| `risk/overlay.py` | `RiskConfig`, `RiskContext`, `build_risk_context(...)` | `PanelView`, the two above |

`build_risk_context` is the **only** function that reads the panel. It receives the
already-masked view, so causality is inherited from the same `masked_to(signal_date(...))`
contract everything else obeys, and `validation/causality.py` truncate-and-compare reaches
it because the context is rebuilt from the truncated panel on every call.

### 4.2 Call shape — identical on both paths

```
sig   = signal_date(sessions, t)
view  = panel.masked_to(sig)
slate = mask_unquoted(strategy.target_weights(view), panel, sig, cols)
risk  = build_risk_context(view, slate, sizing_cfg, risk_cfg, k_prev)  # only panel reader
book  = resolve_book(slate, current, sizing_cfg, stale, risk=risk)     # plain data only
k_prev = risk.applied_k                                                # carried forward
```

`run_backtest` and `compute_live_targets` execute these same lines. `risk=None` is the
passthrough path: benchmarks, null fixtures, and the Reference Clenow profile behave
byte-identically to today.

### 4.3 The sizing circularity, resolved

The scalar needs `k = min(1, target_vol / √(w'Σw))`, but `w` is decided inside
`resolve_book`. Resolution: `RiskContext` stores Σ and exposes `scalar(w) -> float` — pure
arithmetic on stored data, no panel access. Σ is estimated over the top `max_positions`
names in slate rank order, which covers every fundable name: the budgeted fill walks strict
rank order and terminates, so the funded set is always a subset of the first
`max_positions` ranked eligible names, and later pipeline stages only drop names, never add.

### 4.4 `RiskContext` (frozen dataclass)

| field | content |
|---|---|
| `sigma` | Σ over the ranked candidate set (annualized, capital basis) |
| `avg_corr` | average pairwise correlation implied by the pre-shrinkage estimate — recorded for the future correlation-breakdown brake |
| `adv_cap_w` | per-name weight ceiling from the ADV cap (Series) |
| `spread_blocked` | names barred from NEW entry by the spread gate (frozenset) |
| `sector` | symbol → GICS sector label (Series; NaN → `"UNKNOWN"`) |
| `k_prev` | ratchet state carried in |
| `applied_k` | property — ratchet output for this rebalance. `scalar(w)` computes it during resolution and records it in the mutable `diagnostics` record (dict mutation is legal inside a frozen dataclass); the property reads it back. Reading it before resolution raises |
| `beta` | property — portfolio beta vs SPY, computed on the RESOLVED book (it is monitor-only, so the final book is the right object) and recorded into `diagnostics` alongside `applied_k`. NaN allowed |
| `diagnostics` | mutable dict: `applied_k`, `beta`, which caps bound, eigenvalue clips, fallback activations |

### 4.5 New durable state

`k_prev` is one float of path state, the same class of thing as `stale_periods`:

- `BacktestResult` gains `risk_k: pd.Series` (applied k per rebalance) and `final_k: float`
  (for walk-forward fold carry-over, like `final_weights`/`final_stale`).
- Golden replay pins `risk_k` at every rebalance.
- The order service must persist `k_prev` between runs and supply it explicitly.
- `compute_live_targets` gains optional `risk_cfg` and `k_prev` arguments with the same
  guard pattern as `sizing`/`current`: **if `risk_cfg` is supplied, `k_prev` is required.**
  An unknown ratchet state must not silently default to fully-risked; a genuinely fresh
  book passes an explicit `k_prev=1.0` and says so.

### 4.6 `PanelView` change

`PanelView` gains `gics_sector: pd.Series` (symbol → label), loaded by `build_panel` from
`metadata.parquet` alongside `assetid`. Not time-indexed; `masked_to` passes it through
unchanged — which is exactly the declared point-in-time approximation of §3. A snapshot
whose metadata lacks the `gics_sector` column entirely is a schema regression and
`build_panel` raises; per-name NaN is handled by the `"UNKNOWN"` bucket (§6).

## 5. Frozen parameters (`RiskConfig`)

Declared a priori, before any code runs. Zero searched dimensions.

| param | value | rationale |
|---|---|---|
| `target_vol` | 0.10 | §8 verbatim; Carver half-Kelly against honestly expected live SR 0.2–0.5 |
| `up_step` | 0.10 per rebalance | full re-risk from a halving takes ~5 weekly rebalances — "slow up" without freezing in fear. Down moves: unlimited, immediate |
| `ewma_halflife` | 63 sessions | ~1 quarter: stable on ~25 names, sees a regime turn within a quarter |
| `ewma_window` | 252 sessions | causal lookback fed to the EWMA; matches the momentum lookback scale |
| `min_obs` | 40 sessions | below this a variance estimate is noise; near-unreachable given eligibility filters require 252d+ history |
| `shrinkage` | 0.30 toward constant-correlation target | fixed intensity, deliberately NOT Ledoit–Wolf optimal — a data-driven intensity would be a fitted quantity; a declared constant keeps the layer parameter-free in the ledger sense |
| `sector_cap` | 0.25 | §8 verbatim |
| `top3_cap` | 0.25 | §8 verbatim |
| `adv_cap` | 0.25 × 20-day ADV | §8 verbatim; ADV in dollars = `raw_close × volume`, 20-session mean, signal-date-causal (same convention as `engine/backtest._one_way`) |
| `spread_mult` | 2.0 × rolling median | §8 verbatim; Corwin–Schultz over a 21-session estimation window vs a 252-session rolling median of the same estimate |
| `beta_band` | [0.3, 0.8] | deployable profile measured beta 0.50; headroom below because the regime gate legitimately drives beta toward 0. Breach = 4 consecutive out-of-band rebalances, recorded in diagnostics from day one; the actual PAGE action lands with the order service (no live alerting path exists yet) |
| `beta_window` | 252 sessions | standard one-year beta |

The two numbers with the least theory behind them are `shrinkage=0.30` and
`ewma_halflife=63`. They are declared, not fitted; if the on/off ablation makes either look
pathological, the remedy is a declared amendment (new pre-registration, Viktor sign-off),
never a search.

## 6. Decision math — pipeline order (normative)

`resolve_book` with `risk` supplied runs:

```
1.  admission      regime gate AND spread gate (sym ∉ spread_blocked).
                   Spread gate blocks NEW entry only — held names are always
                   retainable (§8: "no new entries", never a forced exit on a
                   liquidity signal).
2.  budgeted fill  unchanged.
3.  position cap   cap_i = min(position_cap, adv_cap_w[i]) — per-name min of caps.
4.  sector cap     per sector: if Σ w_i > sector_cap, scale that sector's names
                   down proportionally. Shortfall → cash, NOT redistributed.
5.  top-3 cap      if the 3 largest sum > top3_cap, scale those 3 down
                   proportionally; iterate to fixed point (see invariants).
6.  gross norm     unchanged (gross_max).
7.  vol scalar     k_raw = min(1, target_vol / sqrt(w' Σ w)) on the POST-cap book;
                   applied_k = ratchet(k_raw, k_prev, up_step); w *= applied_k.
8.  floor          unchanged — still AFTER all scalars (k can push a name under $1k;
                   dropping only lowers the sum, one pass remains the fixed point).
9.  drift band     unchanged.
10. re-validate    validate_book + sector, top-3, and ADV checks.
```

### Invariants and rationale

- **Caps before scalar.** Caps shape the book's relative structure; the scalar sets its
  level. Scalar-first would shrink positions under their caps so the caps never bind, and
  the ratchet would then re-risk into an uncapped structure. Cap-first is idempotent under
  scaling: sector and top-3 caps are homogeneous in `w` as weight *shares* — multiplying by
  k ≤ 1 cannot re-violate them, and gross only shrinks.
- **Scalar measured on the post-cap book.** That is the book actually held; measuring
  pre-cap would target the vol of a book we never hold.
- **Sector scale-down, never redistribute.** Redistribution would hand weight to
  lower-ranked names the budgeted fill did not choose — a second, hidden fill. Shortfall to
  cash matches the floor semantics already settled in the sleeve spec.
- **Top-3 is a fixed-point iteration.** Scaling the 3 largest down can promote a 4th name
  into the top 3. Recompute the 3 largest, rescale, repeat: each pass strictly reduces the
  top-3 sum while it exceeds the cap, weights only fall and are bounded below, so it
  converges (≤ 2–3 iterations in practice). Top-3 scaling cannot create a *sector* breach
  (it only shrinks weights), so sector-then-top-3 needs no outer loop. A constructed
  pathological case pins this in tests.
- **Drift band after scalar.** The band compares target vs currently-held weights; k is
  part of the target. A band-retained name keeps its old k-scaled weight — consistent with
  existing semantics, and `forced_resize_periods` already bounds how stale a retained k can
  get.
- **Ratchet never blocks a downward move.** The future brakes spec pushes k down below the
  formula; §8's "brakes override the formula, not vice versa" composes with the ratchet by
  construction.

### Fallbacks (fail-closed, all logged in `diagnostics`)

- Name with < `ewma_window` history: variance from available data, floored at the
  cross-sectional median variance. Below `min_obs`: barred from new entry and excluded
  from the Σ candidate set (conservative; near-unreachable given eligibility filters).
  A HELD name that falls below `min_obs` (e.g. a long halt) stays in Σ via the variance
  floor — the exclusion applies to new entries only, so `scalar(w)` never meets a funded
  weight it has no row for.
- Σ not PSD after shrinkage: clip negative eigenvalues at 0.
- Per-name missing GICS: pseudo-sector `"UNKNOWN"`, itself subject to `sector_cap` —
  unknown-sector risk is capped, not exempt.
- SPY history insufficient for beta: `beta = NaN`. Diagnostic only; beta is never a sizing
  input.

## 7. Error handling

- `build_risk_context` raises on: an empty candidate set against a non-empty slate; Σ
  containing NaN after fallbacks; `k_prev` outside (0, 1]. Fail-loud at construction, like
  `validate_book`.
- `compute_live_targets(risk_cfg=...)` without `k_prev` raises (§4.5).
- Snapshot metadata missing the `gics_sector` column: `build_panel` raises (§4.6).
- The trading gate is untouched: `risk_layer_version` remains `None` until Viktor sets it
  after the production-profile gauntlet re-run. This PR must not set it.

## 8. Testing

- **`covariance`:** EWMA weight decay correct; shrinkage moves off-diagonals toward the
  constant-correlation target; PSD clip; `avg_corr` matches a hand-computed 3×3.
- **`spread`:** Corwin–Schultz reproduces the closed form on a synthetic two-day fixture;
  negative estimates floor at 0.
- **`overlay`:** ratchet (down immediate, up capped at `up_step`, stable at 1.0); scalar
  never exceeds 1 (no leverage); sector proportional scale-down incl. `"UNKNOWN"`; top-3
  fixed point on the constructed pathological case; ADV cap min-composition; spread gate
  blocks entry but not retention.
- **`resolve_book(risk=...)`:** k ≤ 1 preserves all caps (the cap-then-scalar invariant);
  floor runs after k; **`risk=None` is byte-identical to today** — regression pin for the
  Reference profile and benchmarks.
- **Parity:** golden replay extended to pin `risk_k` per rebalance;
  `compute_live_targets(risk_cfg, k_prev)` ≡ engine weights at every rebalance.
- **Causality:** an overlay analogue of `LookaheadTrap` — a Σ built from the unmasked
  panel must be caught by truncate-and-compare (the causality factory takes the panel, so
  the existing harness reaches it).
- Estimator tests construct `RiskContext` literals; no panel needed outside the
  `build_risk_context` tests themselves.

## 9. Gauntlet wiring and the ablation

- The deployable profile definition gains the overlay. The Reference Clenow profile does
  not (fidelity evidence stays faithful to the source).
- Monkey, walk-forward, DSR machinery: unchanged. The overlay lives inside `resolve_book`,
  so matched monkeys (`ClenowMomentum(shuffle_seed=·)`) inherit it automatically — the
  null stays matched, which is exactly what made the drawdown finding visible.
- Walk-forward folds carry `final_k` into the next fold alongside `final_weights` and
  `final_stale`.
- **One pre-registered run:** overlay-on vs overlay-off on the deployable profile, same
  snapshot, reported like the gap-filter ablation — a measured cost/benefit, not an
  optimization target. Zero searched dimensions; no `family_trials` increment beyond the
  registered run itself.
- Success criteria for the ablation report: monkey drawdown percentile on the overlay-on
  book (did the measured concentration actually fall?), realized vol vs the 10% target,
  CAGR/Sharpe cost of the overlay, cap bind rates by stage, and the `applied_k` path
  through 2008/2020/2022.

## 10. Open items this spec deliberately leaves behind

- Brake thresholds (95th −49.5% / 99th −57.7% from the calibration bootstrap are the
  *inputs* to that spec, recomputed on the overlay-on book).
- The correlation-breakdown brake's definition of "sustained spike" — `avg_corr` is
  recorded per rebalance from day one so that spec has history to work with.
- Whether Norgate stores point-in-time GICS (investigate only if the ablation shows the
  sector cap driving results).
- Idle-cash T-bill sleeve (§8) — order-service concern.
