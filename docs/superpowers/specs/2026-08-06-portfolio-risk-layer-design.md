# Portfolio Risk Layer — Design Spec

**Date:** 2026-08-06 (amended 2026-08-07 after multi-model review)
**Status:** approved design, pre-implementation
**Blueprint:** §8 (risk constitution), §6 (gauntlet) — with two declared amendments, see §11
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
band). It is stage 2 and part of stage 3 of the §8 four-stage sizing pipeline (with the
stage order amended — §11).

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
| Point-in-time GICS | **Declared approximation, hardened** (§4.6): the snapshot's `gics_sector` labels the whole history. Known look-ahead; both major reshuffles are named (2016 Real Estate carved out of Financials; 2018 Communication Services absorbing GOOGL/META/DIS-class names); delisted names carry their last-known sector, which is closer to PIT than living names' current labels. Each immutable snapshot records the map as of its `db_date`, so a genuine PIT series accrues from 2026 forward. The ablation reports sector-cap bind rates split at the 2016 and 2018 boundaries so contamination is visible rather than assumed away (§9) — replacing the earlier circular "revisit if the ablation shows the cap driving results" trigger |
| Portfolio vol estimator | **Ex-ante covariance:** EWMA of daily **total-return** (`tr_close`) log returns, shrunk toward a constant-correlation target. TR, not capital: the vol target's 10% is defined on the equity curve, and P&L runs on `tr_close` — risk measurement is a P&L-side reader under the basis rule. Distinct from the cost model's sigma, which deliberately stays on `px_close` (impact estimation; dividend drift is not tradeable volatility). Sees concentration the same rebalance the strategy creates it; yields `avg_corr` for free |
| Anti-procyclicality mechanic | **Rate-limited ratchet:** down moves immediate and in full; up moves capped at `up_step` per rebalance. State is one float, `k_prev`. Frozen (not advanced) while the book holds no meaningful risk (§6) |
| Parameters | **All frozen a priori.** Zero searched dimensions, zero trials consumed, no DSR interaction. One on/off ablation, report-only. Any later change is a declared constitution amendment with Viktor's sign-off — never a tuning loop |
| Beta band breach | **Monitor + page only.** Long-only, the only sizing lever is exposure. Note the honest limit of the earlier "the vol scalar already pulls it" argument: vol and beta are correlated but not collinear (a low-vol high-beta book exists), so the band is a genuine second diagnostic, not a redundant one — it just has no safe automatic action in a long-only book. Page after 4 consecutive out-of-band rebalances; never a sizing input |
| Architecture | **`RiskContext` computed before the resolver** (option C): all panel reads in one function, resolver stays a pure function of plain data |
| Cap-first pipeline order | Caps shape the book, then the scalar sets its level — **a declared amendment to blueprint §8's stage order**, see §11 |

## 4. Architecture

### 4.1 Modules

| module | job | depends on |
|---|---|---|
| `risk/covariance.py` | EWMA covariance + constant-correlation shrinkage; returns Σ and average pairwise correlation | numpy/pandas |
| `risk/spread.py` | Corwin–Schultz spread estimate from `px_high`/`px_low`; lagged rolling-median comparison | numpy/pandas |
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
risk  = build_risk_context(view, slate, current, sizing_cfg, risk_cfg, k_prev)  # only panel reader
book, applied_k = resolve_book(slate, current, sizing_cfg, stale, risk=risk)    # plain data only
k_prev = applied_k                                                              # carried forward
```

`run_backtest` and `compute_live_targets` execute these same lines. `risk=None` is the
passthrough path: benchmarks, null fixtures, and the Reference Clenow profile behave
byte-identically to today (and receive the book alone, exactly the current signature).

Note `build_risk_context` takes `current`: the Σ candidate set must include held names
(§4.3), and admission logic (spread gate, `min_obs` bar, `admit_new`) is applied *inside*
`build_risk_context` when selecting candidates — the same exclusions `resolve_book` later
applies, computed from the same inputs, so the two cannot disagree.

### 4.3 The sizing circularity, resolved

The scalar needs `k = min(1, target_vol / √(w'Σw))`, but `w` is decided inside
`resolve_book`. Resolution: `RiskContext` stores Σ and exposes `scalar(w)` — pure
arithmetic on stored data, no panel access.

**Σ's candidate set must contain every name the resolver can fund.** Raw slate rank order
is NOT sufficient: a spread-blocked or `min_obs`-barred name inside the top
`max_positions` makes the budgeted fill walk past rank `max_positions`, and under
regime-off (`admit_new=False`) retention can fund a held name of any rank. Therefore the
candidate set is:

> the first `max_positions` names of the **admitted** rank order (spread gate, `min_obs`
> bar, and `admit_new` applied — the same admission `resolve_book` performs) **∪ all
> currently held names** (`current > 0`).

With that construction, funded ⊆ candidates by construction: the fill only walks the
admitted rank order, later stages only drop names, and retention only keeps held names.
`scalar(w)` raises if it meets a funded weight with no Σ row — that is a construction bug,
never a silent reindex-and-drop (which would understate risk exactly during the
liquidity-stress episodes that trip the spread gate).

### 4.4 `RiskContext` (frozen dataclass)

| field | content |
|---|---|
| `sigma` | Σ over the candidate set of §4.3 (annualized, total-return basis) |
| `adv_cap_w` | per-name weight ceiling from the ADV cap (Series) |
| `spread_blocked` | names barred from NEW entry by the spread gate (frozenset) |
| `sector` | symbol → GICS sector label (Series; NaN → `"UNKNOWN"`) |
| `k_prev` | ratchet state carried in |

`scalar(w) -> ScalarResult` is a pure method: given a weight vector it returns a small
frozen result `(applied_k, k_raw, sigma_p)` and mutates nothing. `resolve_book` calls it
at the scalar stage and **returns `applied_k` explicitly alongside the book** — no hidden
state, no mutable-diagnostics trick, no call-order coupling on the money path.
Post-resolution diagnostics that need the final book — `beta`, funded-book `avg_corr`,
which caps bound — are computed by a separate pure function
`risk_diagnostics(ctx, view_or_stored_inputs, book) -> dict` and recorded by the caller;
they are never inputs to sizing.

`avg_corr` is recorded for the future correlation-breakdown brake and is measured on the
**funded book** (equal-weight mean of the upper triangle of the pre-shrinkage correlation
submatrix over funded names) — a candidate-universe average is a different, less relevant
quantity.

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

The beta-band breach rule ("4 consecutive out-of-band rebalances") introduces **no**
additional durable state: the streak is derived from the recorded per-rebalance beta
series (the backtest reads its own record; the order service reads its rebalance log).

### 4.6 `PanelView` change, and the GICS approximation

`PanelView` gains `gics_sector: pd.Series` (symbol → label), loaded by `build_panel` from
`metadata.parquet` alongside `assetid`. Not time-indexed; `masked_to` passes it through
unchanged — which is exactly the declared point-in-time approximation. A snapshot whose
metadata lacks the `gics_sector` column entirely is a schema regression and `build_panel`
raises; per-name NaN is handled by the `"UNKNOWN"` bucket (§6).

The approximation, stated honestly: applying the snapshot's sector map to 2004–2026 uses
labels not knowable on historical signal dates. The two structural reshuffles — 2016
(Real Estate out of Financials) and 2018 (Communication Services) — relabel material
slices of the index retroactively, so historical sector-cap binds are measured against a
map the live system would not have had. Partial mitigations: delisted names carry their
last-known sector (closer to PIT than living names' current labels), and every snapshot
from 2026 forward records its own map, so a true PIT series accrues. The ablation makes
the contamination *visible* by reporting sector-cap bind rates split at the 2016 and 2018
boundaries (§9). Whether Norgate stores historical GICS remains uninvestigated — a
deliberate scope decision, revisitable as a declared follow-up, not silently.

## 5. Frozen parameters (`RiskConfig`)

Declared a priori, before any code runs. Zero searched dimensions.

| param | value | rationale |
|---|---|---|
| `target_vol` | 0.10 | §8 verbatim; Carver half-Kelly against honestly expected live SR 0.2–0.5 |
| `up_step` | 0.10 per rebalance | full re-risk from a halving takes ~5 weekly rebalances — "slow up" without freezing in fear. Down moves: unlimited, immediate |
| `ewma_halflife` | 63 sessions | ~1 quarter: stable on ~25 names, sees a regime turn within a quarter |
| `ewma_window` | 252 sessions | causal lookback fed to the EWMA; matches the momentum lookback scale |
| `min_obs` | 40 sessions | below this a variance estimate is noise; near-unreachable given eligibility filters require 252d+ history |
| `shrinkage` | 0.30 toward constant-correlation target | fixed intensity, deliberately NOT Ledoit–Wolf optimal — a data-driven intensity would be a fitted quantity; a declared constant keeps the layer parameter-free in the ledger sense. Note the effective sample (halflife 63 ≈ 180 effective obs) is thin against ~325 free entries for a 25-name book — the fixed intensity is a conservative simplification, and the estimator contract below exists because this fallback path WILL fire |
| `sector_cap` | 0.25 | §8 verbatim |
| `top3_cap` | 0.25 | §8 verbatim |
| `adv_cap` | 0.25 × 20-day ADV | §8 verbatim; ADV in dollars = `raw_close × volume`, 20-session mean, signal-date-causal (same convention as `engine/backtest._one_way`). Will not bind at $50k in S&P names — forward-looking, fail-closed protection for halts/removals (predecessor spec §3) |
| `spread_mult` | 2.0 × lagged rolling median | §8 verbatim; see spread-gate contract below |
| `spread_floor` | 0.0010 (10 bp relative spread) | the block threshold is `max(spread_mult × median, spread_floor)` — CS on liquid large caps is frequently zero-floored, so a raw `2 × median` can be `2 × 0` and block on noise |
| `beta_band` | [0.3, 0.8] | deployable profile measured beta 0.50; headroom below because the regime gate legitimately drives beta toward 0. Breach = 4 consecutive out-of-band rebalances, recorded from day one; the actual PAGE action lands with the order service (no live alerting path exists yet) |
| `beta_window` | 252 sessions | standard one-year beta |

The two numbers with the least theory behind them are `shrinkage=0.30` and
`ewma_halflife=63`. They are declared, not fitted; if the on/off ablation makes either look
pathological, the remedy is a declared amendment (new pre-registration, Viktor sign-off),
never a search.

### Covariance estimator contract

Return basis: daily log returns of `tr_close` (§3). Then:

- **EWMA weights** over the trailing `ewma_window` sessions, halflife `ewma_halflife`,
  **renormalized to sum to 1 over the truncated window**.
- **Alignment policy:** complete-case over the candidate set's common sessions within the
  window; a name's non-trading sessions (halt, late listing) are excluded pairwise with a
  declared minimum of `min_obs` overlapping observations per pair — below that the pair's
  correlation falls back to the shrinkage target's constant correlation (conservative:
  unknown correlation is assumed average, not zero).
- **Shrinkage target:** constant-correlation matrix with ρ̄ = mean of the upper triangle
  of the pre-shrinkage correlation estimate, **clipped to [−1/(N−1), 1]** so the target
  itself is PSD; target diagonal = the EWMA variances.
- **PSD repair:** if the shrunk Σ still fails PSD, clip negative eigenvalues to zero
  (`numpy.linalg.eigh`) **and rescale to restore the pre-clip diagonal** — plain clipping
  silently changes every name's variance. Log the event.
- **Variance floor:** a name with < `ewma_window` history uses available data, floored at
  the cross-sectional median variance. A HELD name below `min_obs` (e.g. a long halt)
  stays in Σ via the floor and target-correlation fallback — the `min_obs` *entry bar*
  applies to new entries only, so `scalar(w)` never meets a funded weight it has no row
  for.

### Spread-gate contract

- Two-day Corwin–Schultz estimates (dimensionless relative spread — CS is already
  price-normalized), negative values floored at 0, aggregated as the **median over the
  trailing 21 sessions**.
- Baseline: rolling median of the same 21-session statistic over 252 sessions **ending 21
  sessions before the signal date** — the baseline must not contain the episode it is
  judging, or a real blowout contaminates its own reference.
- Block new entry iff `current_21d > max(spread_mult × baseline, spread_floor)`.
- Names with insufficient history for the baseline are not blocked by the gate (the
  `min_obs` bar and eligibility filters own that case).
- CS is a continuous-market proxy; the gate is a conservative admission heuristic, NOT an
  estimate of MOC-auction execution cost. Do not read its level as a cost forecast.
- Known limitation, accepted: in a systemic liquidity event many names trip the gate
  together; the gate blocks entries while the book keeps holding (fail-closed on adding
  risk, never a forced exit — §8's "no new entries" rule).

## 6. Decision math — pipeline order (normative)

`resolve_book` with `risk` supplied runs:

```
1.  admission      regime gate AND spread gate (sym ∉ spread_blocked).
                   Blocks NEW entry only — held names are always retainable.
2.  budgeted fill  unchanged.
3.  position cap   cap_i = min(position_cap, adv_cap_w[i]) — per-name min of caps.
4.  sector cap     per sector: if Σ w_i > sector_cap, scale that sector's names
                   down proportionally. Shortfall → cash, NOT redistributed.
5.  top-3 cap      if the 3 largest sum > top3_cap, scale those 3 down
                   proportionally; iterate to fixed point under the termination
                   contract below.
6.  gross norm     unchanged (gross_max; scale-DOWN only — restated because the
                   invariant proof below depends on it).
7.  drift band     on STRUCTURAL weights: compare the capped target against
                   current/k_prev (holdings descaled by the k that produced them).
                   Retention keeps the structural weight; the repair pass extends
                   to ALL caps (position, ADV, sector, top-3, gross).
8.  vol scalar     result = risk.scalar(w_structural); w *= result.applied_k.
9.  floor          unchanged — AFTER all scalars (k can push a name under $1k;
                   dropping only lowers the sum, one pass remains the fixed point).
10. re-validate    validate_book extended: position, gross, sector, top-3, ADV.
```

### Why the band moved before the scalar (amendment to the first draft)

The first draft placed the band after the scalar. Review caught two defects in that
ordering. (a) A k reduction of less than `drift_band` scales every target by the same
relative amount, so every held name lands in-band and the entire vol cut is suppressed —
directly contradicting "down moves immediate and in full". (b) Band retention restores
held weights that the new caps never checked, so a retained weight can breach sector,
top-3, or ADV limits and the final validation would *raise* — turning an intended resize
into a failed rebalance.

Banding **structural** (pre-k) weights fixes both: band decisions become k-independent
(retention compares like with like: this week's structural target vs last week's
structural holding, reconstructed as `current/k_prev`), and every k move — up or down —
passes through to executed weights in full. The cost is honest and accepted: the band no
longer suppresses turnover caused by k jitter; the ratchet's `up_step` quantization
bounds upward jitter, and downward moves are constitutionally required to execute.

The extended repair pass keeps the band's output feasible: any retention that breaches a
cap on the structural book is forced back to its target (the existing pattern for
position-cap breaches, generalized), so step 10 validates a book that is feasible by
construction rather than by luck.

### Invariants and rationale

- **Caps before scalar.** Caps shape the book's relative structure; the scalar sets its
  level. Scalar-first would shrink positions under their caps so the caps never bind, and
  the ratchet would then re-risk into an uncapped structure.
- **The scaling invariant, stated precisely.** Sector, top-3, position, ADV, and gross
  limits are *absolute-weight upper bounds* (e.g. `Σ_{i∈S} w_i ≤ 0.25`). Every such bound
  is preserved by multiplying the vector by any common factor `k ∈ [0, 1]`, and a fortiori
  by per-name shrinks (floor drops). The proof requires that no stage between the caps and
  the scalar ever scales weights UP — hence gross normalization is restated as scale-down
  only, and any future "invest up to gross_max" change would break the invariant and must
  re-derive the ordering.
- **Scalar measured on the structural post-cap book.** `w'Σw` at k=1 measures the shaped
  book's risk; `applied_k` then sets its level. (The realized book's vol is
  `applied_k × sqrt(w'Σw)` by construction.)
- **Sector scale-down, never redistribute.** Redistribution would hand weight to
  lower-ranked names the budgeted fill did not choose — a second, hidden fill. Shortfall to
  cash matches the floor semantics already settled in the sleeve spec.
- **Top-3 termination contract.** Scaling the 3 largest can promote a 4th name into the
  top 3, so iterate: recompute the 3 largest, rescale, repeat. Deterministic tie-break by
  `(weight, assetid)` with a stable sort (the repo's existing convention); convergence
  tolerance `1e-12` (the module's `_TOL`); hard cap of `max_positions` iterations, raising
  on non-convergence; and a final direct check of the constraint regardless of the path
  taken. Monotone bounded iteration guarantees convergence in the limit, not in N steps —
  the hard cap and final check are what make it a correctness guarantee. Top-3 scaling
  cannot create a *sector* breach (it only shrinks weights), so sector-then-top-3 needs no
  outer loop.
- **Ratchet never blocks a downward move.** The future brakes spec pushes k down below the
  formula; §8's "brakes override the formula, not vice versa" composes with the ratchet by
  construction.
- **Ratchet freezes in cash.** If the structural book is empty or `w'Σw` is below a
  numerical floor (regime-off, all-blocked, or post-floor empty book), `applied_k =
  k_prev` and the ratchet does NOT advance: `k_raw` would be 1 by convention (no risk to
  scale), and letting `k_prev` crawl to 1.0 over a cash period would grant a full-size
  re-entry that "slow up" exists to forbid. Re-risking advances only while meaningful
  risky exposure is actually held. (Note the asymmetry is preserved: on re-entry, `k_raw`
  is computed from the live Σ, and the ratchet caps only the *up* move from the frozen
  `k_prev`.)
- **k floor, not a crash.** `k_raw` is floored at 0.01 (a 100× vol overshoot is a data
  bug, not a market state); `k_prev` outside `(0, 1]` after that floor raises. The floor
  prevents a float underflow from tripping the guard during the highest-stress rebalance —
  the worst moment to fail loudly instead of degrading conservatively.
- **Correlated caps, honestly.** For a concentrated momentum book the top-3 and sector
  caps frequently bind on the same names — they are overlapping protections, not
  independent ones. The ablation reports how often top-3 binds when sector has not (§9),
  so the "two layers" framing is measured, not assumed.

### Fallbacks (fail-closed, all logged)

- Covariance and spread fallbacks: see the contracts in §5.
- Per-name missing GICS: pseudo-sector `"UNKNOWN"`, itself subject to `sector_cap` —
  unknown-sector risk is capped, not exempt.
- SPY history insufficient for beta: `beta = NaN`. Diagnostic only; beta is never a sizing
  input.

## 7. Error handling

- `build_risk_context` raises on: an empty candidate set against a non-empty slate; Σ
  containing NaN after fallbacks; `k_prev` outside (0, 1]. Fail-loud at construction, like
  `validate_book`.
- `scalar(w)` raises on a funded weight with no Σ row (§4.3) — construction bug, never a
  silent drop.
- `compute_live_targets(risk_cfg=...)` without `k_prev` raises (§4.5).
- Snapshot metadata missing the `gics_sector` column: `build_panel` raises (§4.6).
- Step-10 validation: `validate_book` is extended to take the risk limits (exact API —
  extra parameter vs a wrapping validator — is a plan-level choice, but the backtest and
  live path MUST run the same extended check, or golden replay pins a weaker invariant
  than production enforces).
- The trading gate is untouched: `risk_layer_version` remains `None` until Viktor sets it
  after the production-profile gauntlet re-run. This PR must not set it.

## 8. Testing

- **`covariance`:** EWMA weight decay + truncated-window renormalization; shrinkage moves
  off-diagonals toward the clipped constant-correlation target; PSD repair restores the
  pre-clip diagonal; pairwise-min-obs fallback to target correlation; `avg_corr` matches a
  hand-computed 3×3; halted-name masking.
- **`spread`:** Corwin–Schultz reproduces the closed form on a synthetic two-day fixture;
  negative estimates floor at 0; the zero-median liquid-name case does NOT block (floor
  term governs); the baseline lag excludes the current episode (a synthetic blowout must
  still trigger).
- **`overlay`:** ratchet (down immediate, up capped at `up_step`, stable at 1.0, frozen on
  an empty/cash book); `k_raw` floor; scalar never exceeds 1; sector proportional
  scale-down incl. `"UNKNOWN"`; top-3 termination contract (tie-break, max-iter raise,
  pathological promotion case); ADV cap min-composition; spread gate blocks entry but not
  retention.
- **`build_risk_context`:** candidate set = admitted top-`max_positions` ∪ held — fixture
  where a spread-blocked top-rank name forces the fill past `max_positions` and the funded
  book still has full Σ coverage; regime-off retention of an arbitrarily-ranked held name.
- **`resolve_book(risk=...)`:** the scaling invariant (k ≤ 1 preserves all caps); floor
  runs after k; structural drift band — a sub-`drift_band` k move still executes in full
  (the suppression regression); band retention that would breach sector/top-3/ADV is
  repaired; **`risk=None` is byte-identical to today** — regression pin for the Reference
  profile and benchmarks.
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
- Success criteria for the ablation report:
  - monkey drawdown percentile on the overlay-on book (did the measured concentration
    actually fall?);
  - **realized post-k vol vs the 10% target** — the path, not just the k series: the
    ratchet bounds k, not delivered vol, and momentum turnover can move `w'Σw` under a
    bounded k (the review's sharpest point about the mechanic);
  - CAGR/Sharpe cost of the overlay;
  - cap bind rates by stage, with sector-cap binds **split at the 2016 and 2018 GICS
    boundaries** (§4.6) and top-3-binds-without-sector-binds reported separately (§6);
  - the `applied_k` path through 2008/2020/2022;
  - an explicit note that ADV-cap no-binds at $50k are expected and are NOT evidence the
    mechanism works.

## 10. Open items this spec deliberately leaves behind

- Brake thresholds (95th −49.5% / 99th −57.7% from the calibration bootstrap are the
  *inputs* to that spec, recomputed on the overlay-on book).
- The correlation-breakdown brake's definition of "sustained spike" — funded-book
  `avg_corr` is recorded per rebalance from day one so that spec has history to work with
  (noting the series inherits the estimator's thin-sample noise; the brake's job includes
  distinguishing spike from noise).
- Whether Norgate stores point-in-time GICS — declared follow-up (§4.6), owner Viktor.
- Idle-cash T-bill sleeve (§8) — order-service concern.

## 11. Constitution amendments this spec declares (Viktor sign-off required)

Per CLAUDE.md's conflict rule these are surfaced, not averaged; the blueprint text should
be updated to match when this spec is approved.

1. **§8 sizing-pipeline stage order.** Blueprint: (2) vol-target scalar, then (3) caps.
   This spec: caps first, scalar second (§6 rationale: scalar-first lets the caps never
   bind and the ratchet re-risk into an uncapped structure; cap-first is invariant under
   the scalar by the scaling argument). The four-stage *inventory* is unchanged — only the
   order of stages 2 and 3.
2. **§9 volatility estimator.** Blueprint standardizes a `0.30·long-run + 0.70·EWMA(span
   ≈ 32d)` blend for vol forecasts. This spec uses EWMA(halflife 63) covariance with 0.30
   constant-correlation shrinkage — a different model in which "0.30" is a shrinkage
   intensity, not a blend weight. Declared here so the two never get conflated; if the
   blueprint's blend is wanted for the *scalar* path, that is a pre-implementation
   amendment to §5 of this spec, not a silent code choice.
