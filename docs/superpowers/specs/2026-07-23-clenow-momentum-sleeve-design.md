# Clenow Momentum Sleeve — Design Spec

**Date:** 2026-07-23 (revised 2026-07-25 after multi-model review; OQ-1/OQ-2 resolved 2026-08-02)
**Status:** Approved — ready for implementation planning
**Phase:** 2 (baseline book on Alpaca paper), first sub-project
**Blueprint refs:** §4.1 (timing contract), §6 (validation gauntlet), §8 (risk constitution), §10 (roadmap)

## 1. Purpose

Implement the primary Phase-2 baseline sleeve — Clenow equity momentum (KB-02, KB-08, KB-11 §9a) —
as a strategy that runs through the existing Phase-1 validation gauntlet, and use it to exercise the
harness against a published system.

**Framing correction (review):** an earlier draft claimed that if the harness cannot reproduce the
published system, "the harness is wrong, not the system." That is false and has been removed. A
correct implementation can legitimately underperform for many reasons — window choice, cash
treatment, fees, vendor differences, or genuine post-publication decay. Replication is **fidelity
evidence**, not an alpha claim. The published parameters are themselves the output of the author's
unknown upstream experimentation; our trials ledger counts our search, not his.

This is the first of several Phase-2 sub-projects. It does **not** cover the ETF trend sleeve, the
order service, or ops reconciliation.

## 2. Resolved questions

**OQ-1 — price basis vs total-return basis. RESOLVED 2026-08-02: Clenow ranks PRICE.**
Confirmed against *Stocks on the Move* (owner: Viktor). The dissenting reviewer's total-return claim,
sourced from secondary web material, is overruled by the book.

**Consequences, now in scope (§3):** a price basis cannot be derived from what the snapshot stores
(evidence below), so the sync must pull a **second, capital-adjusted basis** alongside the existing
total-return series. The `norgate-service` bridge already supports `adjustment="capital"`
(`norgate_api/norgate.py::_adj_map`), so **no VM-side change is required** — the work is confined to
`data/sync.py`, the store schema, QC, and a re-pull that produces a new snapshot id.

Basis assignment:

| Computation | Basis |
|---|---|
| momentum regression, SMA100, regime SMA200, gap filter, ATR20, `close/ATR` ratio | **capital-adjusted (price)** |
| portfolio P&L, equity curve, benchmark comparison | **total-return** |
| MOC fill price, share rounding, ADV, broker reconciliation | raw execution price |

**OQ-2 — annualization factor. RESOLVED 2026-08-02: 250.** Pinned constant, excluded from the searched
parameter space (§6.6).

### Evidence retained: why the price basis must be pulled, not derived

Established empirically against our own snapshot (AAPL, 2020-08-31 4:1 split):

Established empirically against our own snapshot (AAPL, 2020-08-31 4:1 split):

```
2020-08-28   unadjusted_close = 499.23
2020-08-31   unadjusted_close = 129.04
close / unadjusted_close: 0.242493 → 0.969974   (ratio of ratios = exactly 4.0)
```

So `unadjusted_close` is **genuinely raw** — split-unadjusted. It cannot be used for the momentum
regression: every split becomes a −50%/−75% step in `ln(close)`, destroying slope and R² and tripping
the gap filter for `lookback` sessions afterwards. Deriving a price basis from the stored TR series is
therefore impossible — hence the second pull.

**What ranking on the wrong basis would have cost** (quantified during review, retained as the
rationale): ranking on total-return close tilts systematically toward high-dividend names (utilities,
staples, REITs) — precisely what a momentum system should avoid. Roughly 3%/yr of extra annualized
slope on a 3%-yield name over a 90-session window. On the regime gate, TR drift adds ~0.5–1% to the
(price − MA) spread near crossings, biasing marginal days **toward regime-on** — i.e. biasing exposure
upward exactly where the gate is being tested.

**Note on basis mixing (settled):** ATR does **not** need to share a basis with the ranking. Both TR
and split adjustments are multiplicative, so the ratio `close_i / ATR20_i` is invariant to the
adjustment factor. Only mixing bases *inside* that ratio is a bug — combining an adjusted close with
raw high/low creates artificial true ranges around every corporate action. Per OQ-1 every signal
computation uses the capital-adjusted basis, and each computation must be internally consistent within
it.

**Schema:** snapshot columns name their basis explicitly (`tr_open`/`tr_high`/`tr_low`/`tr_close`,
`px_open`/`px_high`/`px_low`/`px_close`, `raw_close`), and the snapshot metadata records which bases
are present — so a future reader cannot mix them by accident, and an old-schema snapshot is detectably
unusable for this sleeve rather than silently wrong.

## 3. Scope

### In scope

- **Dual-basis snapshot (Phase-0 data work, forced by OQ-1):** `data/sync.py` pulls the
  capital-adjusted basis alongside total-return; store schema gains the `px_*` columns; QC extends its
  OHLC-sanity and schema checks to the new basis; snapshot metadata records the bases present; a
  re-pull produces a new snapshot id. Lands and promotes green **before** any strategy code.
- `ClenowMomentum` strategy emitting a `Slate` (§5), plus the shared sizing/resolution layer.
- Book resolution: admission, budgeted top-down fill, caps, floor, normalization, drift band.
- `PanelView` OHLC extension carrying both bases (§7).
- PreRegistration + calibration runs + gauntlet wiring, with the ledger accounting settled up front.
- Gauntlet fixes this strategy forces (§10): walk-forward fold state, monkey matching, closed-loop
  causality.

### Deferred to the portfolio risk-layer spec

Genuinely portfolio-level and shared across sleeves.

- §8 stage-2 portfolio volatility-target scalar and the anti-procyclicality clause.
- Loss brakes (malfunction halts, rate-based de-risking) — thresholds are derived from the production
  book's Monte-Carlo drawdown distribution, so they cannot precede it.
- 25% sector cap and top-3 concentration limit — needs GICS threaded into the panel.
- Liquidity overlay (ADV cap, Corwin-Schultz spread gate, beta band).

**Deferral is safe only under an enforced gate.** A configuration flag is not that gate. Requirements:

1. A hard guard that **refuses non-paper mode** while `risk_layer_version is None`. Documentation is
   not sufficient; this is code.
2. Sequencing for capital: build production profile → estimate MC thresholds → freeze → **re-run the
   full gauntlet on the production profile** → only then capital. Do not go live inside that circular gap.

**Why the vol scalar is non-optional for capital** (review, quantified): 25 positions each targeting a
10bp daily move imply roughly **8% annualized volatility if independent, but ~23% at an average
pairwise correlation of 0.30**. ATR parity equalizes *standalone* dollar movement; it does nothing
about common equity/sector risk. This is the single strongest argument that the deferred layer is a
prerequisite for real money — and it is fine for paper.

**ADV deferral justification (corrected):** at $50k, a 5% position is $2,500 — on the order of 0.02% of
ADV for even the smallest S&P 500 constituent. Economically irrelevant at this size, which is a far
better reason than "it's portfolio-level." It remains cheap fail-closed protection for index removals,
halts and degraded liquidity, so it lands with the risk layer rather than being dismissed.

### Out of scope

Order submission, broker reconciliation, the ETF sleeve, RSI(2) mean reversion.

## 4. Two frozen profiles

The review identified a genuine trap: the configuration that passes the gauntlet must be the
configuration that ships. An earlier draft ran calibration with caps off and production with caps on,
and gated only the former — meaning the ledger would record a "pass" for a system never traded, and
the drawdown gate would read a sector-concentrated book that production would never run.

| Profile | Purpose | Gauntlet |
|---|---|---|
| **Reference Clenow** | Source rules as published; production overlays off. Fidelity evidence only. | Full run; **never** treated as deployable evidence |
| **Deployable sleeve** | Integer shares, costs, all §8 caps, cash return, brakes | Full gauntlet re-run required before capital |

Both profiles are frozen configurations, not a runtime toggle. `caps_enabled` as a single flag is
retired.

## 5. Architecture — the strategy contract

### 5.1 Decision reversed from the previous draft

The previous draft changed the protocol to `target_weights(view, current)`. **That decision rested on
an incorrect premise** — that the strategy needs holdings in order to re-size retained names by current
ATR parity. It does not: ATR-parity weights are per-name and set-independent
(`w_i = risk_factor × close_i / ATR20_i`), so a strategy that emits weights for **all eligible** names
already contains the correct weight for every retained name. The earlier draft conflated *eligible*
with *admitted*.

Three reviewers independently rejected putting holdings inside the strategy. The chosen design is the
strongest of the alternatives.

### 5.2 The `Slate` return type

Change the **return type**, not the signature:

```python
@dataclass(frozen=True)
class Slate:
    weights: pd.Series   # absolute ATR-parity weight for ALL eligible names (unbudgeted)
    rank: pd.Series      # rank over the full point-in-time constituent set
    admit_new: bool      # the regime gate
```

```
ClenowMomentum.target_weights(view) -> Slate          # stateless, pure function of the panel
resolve_book(slate, current, config) -> pd.Series     # in sizing.py; holdings-aware
```

`resolve_book` performs admission, the budgeted top-down fill, caps, floor, normalization and the
drift band, and is called identically by `run_backtest` and `compute_live_targets`.

**Why this over a bare `regime_on` boolean:** a boolean cannot recover the budget-constrained fill.
Under regime-on the fill stops when equity is exhausted (say rank 17); a held name at rank 30 would be
absent from an already-budgeted book and the diff would sell it, whereas correct regime-off behaviour
funds it. Emitting *unbudgeted* weights for all eligible names plus the rank vector preserves that
information. Filter and admit first, normalize afterwards — never normalize across names that will
later be blocked.

**Why this over `target_weights(view, current)`:**

- **The causality proof stays total.** Truncate-and-compare with fixed holdings proves only pointwise
  panel purity; it downgrades the guarantee from "the deployed decision function is causal" to "causal
  at one holdings point, plus a hand-written engine assertion." That total proof is the reason Phase 1
  exists.
- Holdings are already needed by the drift band, sector cap, vol scalar and loss brakes — all in the
  layer being built anyway. Threading them into the strategy too creates two holdings-aware layers.
- `sizing.py` is already shared with the ETF sleeve, so the resolver is reused verbatim.

The middle road (`current: pd.Series | None = None`) is explicitly rejected — that is averaging two
designs rather than choosing one.

**Future note (not this spec):** with a second sleeve, `current` must become a typed `SleeveState`
carrying share counts, sleeve attribution, allocated equity and an as-of timestamp — otherwise one
sleeve can "retain" a position owned by another. Single-sleeve weights are sufficient for now; the
resolver signature should not obstruct that later change.

### 5.3 Two distinct holdings states

The engine must not conflate them:

- **`state_at_signal`** — holdings as of T−1's close. Used for admission/retention and the drift-band
  decision. This is what `resolve_book` receives.
- **`state_at_fill`** — holdings marked through T. Used *ex post* for realized turnover, costs and the
  post-fill book.

The strategy and the resolver must never see the second: live trading cannot know T's closing weights
when the MOC order is submitted that morning. `run_backtest` captures `state_at_signal` at the top of
session `t`, before the earn/drift lines.

### 5.4 Module layout

```
src/number7/strategies/__init__.py
src/number7/strategies/clenow.py     ClenowMomentum, Slate, ranking/filter/regime helpers
src/number7/strategies/sizing.py     SizingConfig, resolve_book, apply_drift_band
```

## 6. Decision math

All computations use data through the signal date (T−1); engine masking enforces this and
`validation/causality.py` proves it.

### 6.1 Ranking

Over the trailing `lookback` = 90 sessions, per candidate:

1. OLS of `ln(px_close)` on ordinal session index `t = 0..89` → slope `b`, `R²`.
   Ordinal (not calendar) spacing is intentional and matches the published method — do not "fix" it.
2. `annualized = exp(b × 250) − 1` (`ann_factor = 250`, pinned per OQ-2).
3. `score = annualized × R²`, ranked descending.

**Ties** break deterministically: score descending, then a stable security identifier — never ticker
order or incidental pandas ordering.

**Guard note:** `R²` here is a *smoothness heuristic*, not a significance measure. Regressing a
near-random walk on time is textbook spurious regression and a driftless walk has substantial expected
`R²` over 90 sessions. This is intentional in the published system. Nobody should later "upgrade" it to
a t-statistic or p-value gate.

### 6.2 Candidate set, rank order, and filters

**Order is pinned: rank the entire point-in-time constituent set first, then apply qualifiers.**
Ranking only the survivors is wrong — if 30 high-scoring names fail the gap test, an eligible name at
raw rank 120 must stay rank 120, not be promoted to 90. The exit rule is defined against the raw rank.

**Candidate set excludes non-constituents.** `build_panel` sets `in_index = True` for all extras, so
SPY (the regime instrument) is currently a buyable candidate and also pollutes the `hold_top_pct`
denominator. The candidate set must be actual index constituents only; the regime instrument and every
non-constituent extra are excluded explicitly.

Qualifiers, applied after ranking:

- rank within the top `hold_top_pct` = 20% of the point-in-time constituent count;
- `close > SMA(close, ma_filter=100)`;
- no overnight gap `|open / prev_close − 1| > gap_threshold = 0.15` within the trailing 90 sessions.

**Gap definition is an implementation decision, recorded as such:** the source alternates between
"gap" and "single daily move"; we use the overnight definition. Norgate defines the open as the first
print from any venue while the close is generally the listing-exchange auction, so vendor-specific
outliers are possible — worth watching in the calibration memo.

### 6.3 Data preconditions (NaN contract)

A symbol is ineligible unless **all** hold. There is no silent NaN path into ranking.

| Quantity | Requirement |
|---|---|
| regression | 90 consecutive valid closes, all `> 0` |
| stock SMA | 100 valid closes |
| TR / ATR | 21+ valid bars; `ATR20 > 0` |
| regime series | 200 valid closes |

Constant log-price leaves `R²` undefined → ineligible. Zero or NaN ATR → ineligible (never an infinite
position). Compressing suspended or missing sessions into ordinal time inflates slopes, so gaps in the
bar sequence disqualify rather than compress.

**Regime warm-up is an explicit branch, not a NaN side effect.** For the first ~200 sessions
`SMA(SPY, 200)` is NaN, and `NaN > x` evaluating to `False` would fall into regime-off by accident.
That fail-safe must be written and tested deliberately.

### 6.4 Regime gate

`admit_new = regime_close > SMA(regime_close, regime_ma=200)`

**Regime instrument, frozen: capital-adjusted SPY** (`px_close`), consistent with OQ-1's price basis.
The published system references the index itself; SPY is a proxy chosen because it is already synced
(`extra_symbols`) and tracks the index closely. Pulling `$SPX` from Norgate's US Indices database is a
registered **variant**, not a free swap — a change of proxy is a strategy variation, and moving to a
total-return index would reintroduce exactly the regime-on bias OQ-1 eliminated. Golden crossing-date
tests pin the chosen series so the proxy cannot drift silently.

Semantics are precisely `allow_open_new_symbols = False` — **not** "no buy orders" and **not**
"the book never grows." Retained names are still re-sized by current ATR parity, which can *increase*
share counts and gross exposure in a downtrend. The previous draft's "the book only shrinks or holds"
was wrong and is corrected.

No hysteresis. Acceptable because the gate is entry-only, which bounds whipsaw cost — stated here so a
future reviewer does not "fix" it.

### 6.5 ATR-parity sizing

`TR_t = max(high − low, |high − prev_close|, |low − prev_close|)`

**Wilder smoothing, pinned:** seed `ATR_20 = mean(TR_1..TR_20)`, then
`ATR_t = (19 × ATR_{t−1} + TR_t) / 20`. Simple-mean smoothing is a **robustness diagnostic, not a
parameter** — Wilder's α = 1/n implies an effective span of ~39 days versus 20, a materially different
system. Burn-in must be specified too: a recursive ATR at bar 25 is seed-dominated, and without a
pinned seed and burn-in the §12 known-answer test has no unique answer.

```
weight_i = risk_factor × close_i / ATR20_i          # ABSOLUTE, not proportional
```

**`∝` is retired.** The previous draft wrote `relative_i ∝ …`, which reads as "normalize to sum 1" —
a different system entirely (inverse-vol weighting, always fully invested, regime gate loses its
de-risking effect, and "under-investment is expected" becomes unreachable). If every eligible name were
normalized, `risk_factor` would cancel and the emergent position count would disappear.

**Prose correction:** `risk_factor = 0.001` is *not* "10bp of equity per position." It is 10bp of
equity per position **per unit of ATR**; the resulting weight depends on the `close/ATR` ratio, which
varies enormously across names. A $100 name with ATR $2 yields a 5% position.

**Emergent-count consequence, now explicit:** with a $50k book the $1k floor is 2%, which implicitly
excludes names with ATR above roughly 5% of price, while the 10% cap clips names below roughly 1%.
Risk parity therefore operates only within roughly a 1–5% ATR band. `max_positions` is likewise **a
binding de-risk parameter in high-volatility regimes**, not housekeeping: at 2008-level volatility the
per-name weight falls to ~2%, so ~50 names would be needed and the cap truncates the book to ~40–60%
invested. This must be stated, because the previous draft claimed position count "emerges purely from
sizing" while also imposing `max_positions` — a contradiction.

### 6.6 Parameter space

Searched: `lookback, atr_window, ma_filter, regime_ma, gap_threshold, risk_factor, hold_top_pct,
max_positions, drift_band`.

**Not parameters** (pinned constants, excluded from the declared space): `ann_factor = 250` (units
constant per OQ-2; it interacts nonlinearly with the R² weighting because the exponential is applied
before the multiply, so varying it reorders names — it is emphatically not a tuning knob),
Wilder-vs-simple smoothing (diagnostic), drift-band relative-vs-absolute (design decision).
Commingling these with real hyperparameters misrepresents the degrees of freedom used for DSR scaling.

**`reentry_blackout_days = 0`** is a recorded decision, not a default: it is Clenow-faithful, and the
wash-sale machinery in `execution/lots.py` handles the tax-detection side. Momentum churn around the
rank boundary will produce sell/rebuy pairs; that is accepted here and revisited with the risk layer.

## 7. `PanelView` extension

ATR needs high/low; the gap filter needs open; OQ-1 requires both bases. `PanelView` currently carries
only `close, volume, unadjusted_close, in_index`.

Extended shape:

| Field | Basis | Used by |
|---|---|---|
| `px_open, px_high, px_low, px_close` | capital-adjusted | ranking, SMA100, regime SMA200, gap, ATR20 |
| `tr_close` | total-return | P&L, equity curve, benchmark |
| `volume`, `in_index` | — | ADV inputs, universe |
| `raw_close` | raw | share rounding, reconciliation (live path) |

`masked_to` slices every frame uniformly, so it extends mechanically. Update `build_panel` and all
construction sites — existing strategies' tests, the equal-weight benchmark, the causality factory,
fixtures.

**Sequencing:** the dual-basis snapshot (§3) must land and promote green first; this extension is the
task immediately after, with the full suite green before any strategy code builds on it. The existing
`close` field is renamed rather than duplicated, so the compiler/tests surface every site that must
choose a basis explicitly — no silent default.

## 8. Book resolution

### 8.1 `SizingConfig`

| Field | Default | Note |
|---|---|---|
| `position_cap` | 0.10 | §8 max single position |
| `min_position_dollars` | 1000 | §8 per-position floor |
| `gross_max` | 1.0 | §8 no leverage |
| `sleeve_equity` | — | **Current** sleeve equity, supplied per call |
| `drift_band` | 0.05 | see §8.3 |

**`book_equity` as a fixed constant is retired.** It is wrong after P&L and wrong once the sleeve holds
only part of the total book; the floor and share rounding need *current* sleeve equity.

### 8.2 `resolve_book` ordering

1. **Admission** — if `slate.admit_new` is false, restrict candidates to names in `current` that remain
   eligible. Otherwise all eligible names.
2. **Budgeted top-down fill** — walk admitted names by rank, assigning each its absolute ATR-parity
   weight, until equity is exhausted or `max_positions` is reached. **The marginal name is skipped, not
   partially filled** — pinned here because the previous draft left it undefined, and the choice changes
   both position count and tail allocations.
   This fill is **always on**; it is Clenow's method, not a cap. (The previous draft contradicted
   itself: §5.3 budgeted inside the strategy while §7.2 disabled normalization with caps off, leaving
   nothing to bound the fill.)
3. **Position cap** — clip to `position_cap`.
4. **Gross normalization** — scale down proportionally if the sum exceeds `gross_max`.
5. **Floor** — drop names below `min_position_dollars / sleeve_equity`. **Applied after all scalars**,
   because normalization can push a surviving $1,050 position below $1,000; iterate to a fixed point or
   leave the shortfall in cash.
6. **Drift band** (§8.3), then **re-validate**.

Sub-1.0 gross is expected behaviour — regime-off periods and ATR parity not consuming equity — and is
not a bug.

### 8.3 Drift band

Relative band on names held and still held (`target_i > 0 and current_i > 0`): keep `current_i` when
`|target_i − current_i| / target_i ≤ drift_band`. Entries and exits always execute.

**Post-band re-validation is mandatory** — the band runs after normalization and can re-violate both
limits:

- several held names drifted up, each within band → kept → post-band gross > 1.0 → leverage, which
  `validate_weights` raises inside `compute_live_targets`, i.e. the order service throws in production;
- a name clipped to exactly `position_cap = 0.10` whose current is 0.104 → `|Δ|/target = 4% ≤ 5%` → kept
  at 0.104 → **cap breached silently, because `validate_weights` does not check `position_cap`**.

Fix: after the band, force the trade for any name whose retention would breach `gross_max` or
`position_cap`. Add `position_cap` to the validation performed on the resolved book.

**Structural caveat:** a relative band bites five times harder on a 10% position than a 2% one, and a
name can drift within band indefinitely, letting ATR-parity risk sizing decay. A forced re-size after
N periods without a trade is the mitigation; N is pinned in the pre-registration.

### 8.4 Live-path holdings construction

`current` in `compute_live_targets` is **broker share counts × the snapshot's T−1 official close ÷
sleeve equity** — never broker market value. The backtest marks holdings at T−1's close while the live
path runs on the morning of T; using broker market value would mark after the open, so the golden-replay
test would pass on a fixture while the live path silently diverged intraday.

**Stale/degraded broker truth degrades to hold-state, no trades** (platform invariant). If holdings
cannot be established, the sleeve trades nothing rather than treating an unknown position as flat — a
misread `current_i > 0` mask would convert a designed hold-through-drawdown into an accidental full exit.

## 9. Engine changes

| Site | Change |
|---|---|
| `Strategy` protocol | `target_weights(view) -> Slate` (return type only; signature unchanged) |
| `RandomTopN`, `LookaheadTrap`, EW benchmark | Return a `Slate` (`admit_new=True`, rank from their own ordering) |
| `run_backtest` | Capture `state_at_signal` at the top of session `t`; call `resolve_book`; keep `state_at_fill` separate for turnover/costs |
| `compute_live_targets` | Gains `current` (§8.4) and calls the same `resolve_book` |
| Golden-replay parity test | Assert equality through resolution and the band; update the fixture |
| `validation/causality.py` | Unchanged in shape — the strategy stays a pure function of the panel, so truncate-and-compare remains a **total** causality proof |

**Known optimistic assumption, recorded:** `run_backtest` sets `w = target` after observing T's return,
assuming exact closing-weight attainment from a morning-submitted MOC order. Not a signal leak, but an
optimistic execution assumption that the paper phase will measure.

## 10. Gauntlet fixes this strategy forces

A path-dependent, part-cash strategy breaks assumptions in three existing stages. None were addressed
in the previous draft; all are in scope here.

1. **Walk-forward folds start flat.** `walkforward.py` builds a fresh strategy per fold and
   `run_backtest` starts in cash, so an OOS fold opening in regime-off can never buy and returns ~0 —
   systematically depressing bear folds and biasing WFE. Fix: carry the IS end-state holdings into the
   OOS segment.
2. **Monkey null is mismatched.** `monkey.py` uses `RandomTopN`, which is always fully invested and
   equal-weight, against a candidate that is often part-cash and ATR-sized. Fix: randomize only the
   *ranking*, passing each monkey through the identical filters, regime gate, sizing and resolution.
3. **Causality is proven pointwise, not closed-loop.** Fixed-`current` truncate-and-compare proves panel
   purity at one holdings point. Add a closed-loop check: run full and truncated simulations from the
   same initial state and compare every overlapping slate, resolved book and transition.

**DSR hurdle is 0.98, not 0.95.** `dsr.py::dsr_hurdle` returns 0.98 whenever
`n_effective_trials < 15` *or* origin is LLM — and a pinned single-point calibration is by definition
low-N. The previous draft's "0.95 for human origin" was simply wrong.

Further, a one-point fidelity replication has **no search**, so DSR is not meaningfully applicable at
N=1. Reference Clenow and any searched variant are therefore **separate pre-registrations**, not one
registration spanning "a narrow range" — blending them is the weakest form of both.

**Ledger accounting, settled before the first run** (otherwise the pre-registration is compromised on
arrival): ablations, the profile pair, and cost-sensitivity runs are declared **diagnostics, excluded
from the DSR trial count**, on the explicit justification that none is a deployment candidate. Any
parameter change made in response to calibration results spawns a **new** pre-registration and counts
as a new trial.

## 11. Calibration

### 11.1 Window

Published results span roughly 1999–2014; our history starts 2004. The overlap (2005–2014, after
warm-up) is usable for quantitative comparison; 2015→present is post-publication validation. The
missing 2000–2003 window removes the dot-com bear — arguably the episode that best justifies a
200-day regime filter — leaving 2008 as the only severe bear in sample.

### 11.2 Gates (rewritten — the previous version had almost no discriminating power)

"Max drawdown materially shallower than SPY's −55%" is passed by *any* system holding meaningful cash,
including one that is 50% cash by accident or has a broken fill loop. It tests nothing about the gate.
Replaced by:

1. **Paired ablation.** Run the identical strategy with the regime gate disabled. The gate's
   contribution is (gated − ungated), a paired comparison with far more power than a comparison to SPY.
2. **All regime-off episodes, not one.** Score every regime-off episode 2004→present (~8–12): hit rate
   (did the off-state precede a drawdown?) and false-positive cost (whipsaw drag). Resting a gate on
   N=1 realization of the event it exists to handle is not a gate.
3. **Exposure-adjusted return.** Under-investment is expected (§8.2), so raw CAGR versus a
   fully-invested SPY through a long bull punishes the design for working as intended. Gate on Sharpe,
   beta, and return per unit of average gross exposure; report **average gross exposure as a
   first-class metric**.
4. **Turnover at regime transitions** specifically, not just average weekly turnover — whipsaw-driven
   spikes are the known SMA-crossing failure mode and an average hides them.
5. **Cost sensitivity:** 0× / realistic / 2× the cost model. A sleeve that dies at 2× is fragile, and
   that is worth knowing before paper rather than after.
6. **Ablations as the strongest check:** no-R² (raw slope), no regime gate, equal-weight instead of ATR
   parity, no gap filter. If the full system cannot beat its own ablations, the implementation is
   suspect; if it crushes them, that is also signal.

### 11.3 Cash rate — must be pinned

The engine currently earns **zero on cash**, while the blueprint routes idle cash to a T-bill sleeve.
With a book averaging perhaps 60% invested, a 0% cash assumption handicaps the strategy by roughly
1–2%/yr over 2004→present (≈5% bills 2006–07, ~0% 2009–15, ~5% 2023–24) — comparable in size to the
entire effect being measured, and regime-off stretches can last months. Pin the backtest cash rate
explicitly and state it in the memo.

### 11.4 Anti-fitting clause

"A discrepancy triggers investigation, not failure" is an open door and is now bounded. Legitimate:
*implementation bug found → fix → re-run*. Not legitimate: *parameter nudged until the chart matches
the book*. Any parameter change spawns a new pre-registration (§10). Without this, a calibration
exercise quietly becomes a fit.

### 11.5 Cadence deviation, recorded

The published system maintains the roster weekly but re-sizes positions every second Wednesday; our
scheduler rebalances weekly (Tuesday default) with MOC fills. This is a **declared platform
adaptation**, not an oversight — recorded so the calibration memo does not attribute the resulting
turnover difference to a bug.

## 12. Test plan

TDD throughout; offline, seeded, no network.

**Known-answer**
- Planted exact log-linear trend → slope and `R²` recovered analytically (`R² ≡ 1.0`).
- `ATR20` hand-computed with the pinned Wilder seed and burn-in.
- Gap filter fires at 15.1%, not 14.9%.
- 100-day MA and 200-day SMA boundary cases (`>` vs `≥`).
- Deterministic tie-break under equal scores.

**Preconditions (§6.3)** — each of: <90 bars, embedded NaN, non-positive close, zero ATR, constant
log-price ⇒ ineligible, never a NaN or infinite weight reaching the book.

**Regime gate**
- Regime off + held name still eligible ⇒ retained and re-sized (including a case where its share count
  *increases*).
- Regime off + new top-ranked name ⇒ not admitted.
- Warm-up (<200 regime bars) ⇒ explicit regime-off branch.

**Candidate set** — SPY and non-constituent extras never appear in the slate, and do not affect the
`hold_top_pct` denominator.

**Resolution** — cap clips; floor applied post-normalization (including the $1,050→sub-$1,000 case);
marginal name skipped not partially filled; budgeted fill active in both profiles.

**Drift band** — 3% ⇒ no trade; 7% ⇒ trades; entries/exits always execute; **retention that would
breach `gross_max` or `position_cap` forces the trade instead**.

**Delisting** — a name whose bars end mid-week is exited at its last available close, neither carried
at a stale price nor silently dropped from the return calculation; the event count is logged over the
full run. State whether the Norgate TR series already embeds a terminal delisting return; if not, the
backtest overstates.

**Index membership** — assert `in_index` reflects *effective* dates, not announcement dates; otherwise
the book trades the S&P-addition pop, a real look-ahead. Deletion-date exits are the classic
worst-execution point — recorded as a known cost.

**Causality**
- `LookaheadTrap` still caught.
- A deliberately leaky Clenow variant is caught.
- Closed-loop full-vs-truncated trajectory comparison (§10.3).
- **Cross-snapshot stability:** the decision for a fixed historical signal date is unchanged across
  later immutable snapshots — a future dividend may rescale pre-event adjusted levels but must leave
  slope, `R²`, MA relations, gap ratios and `close/ATR` unchanged.

**Contract-wide** — `validate_weights` plus the new `position_cap` check on every resolved book
(property test over random panels); golden-replay parity green through resolution and band.

**Suite gate** — all 85 existing tests green; `ruff check src tests` clean.

## 13. Deliverables

- Dual-basis snapshot: `data/sync.py`, store schema, QC extension, metadata basis record, re-pull
- `strategies/clenow.py`, `strategies/sizing.py`
- `PanelView` dual-basis extension
- Engine updates: `strategy.py`, `backtest.py`, `live.py`, parity test
- Gauntlet fixes: `walkforward.py` fold state, `monkey.py` matching, closed-loop causality check
- Non-paper guard keyed on `risk_layer_version`
- Two pre-registrations (reference replication; searched variant)
- Calibration script and memo

## 14. Success criteria

1. Dual-basis snapshot syncs, passes QC, and promotes; metadata records both bases; a snapshot lacking
   the price basis is rejected by the sleeve rather than silently mis-ranked.
2. Gauntlet executed with correct ledger accounting; diagnostics excluded per §10; pre-registration
   precedes every run.
3. Causality green: leaky variant caught, closed-loop trajectory matches, cross-snapshot stable.
4. Golden-replay parity green through resolution and the drift band.
5. Calibration memo written: overlap-window comparison, paired ablation, all regime-off episodes,
   exposure-adjusted metrics, cost sensitivity, explicit cash rate, and the cadence deviation stated.
6. Suite green, `ruff` clean.
7. Non-paper guard verified to refuse live mode without the risk layer.

A gauntlet **failure is an acceptable outcome** and is documented as a kill. This is a fidelity
exercise, not a search for a passing grade.

## 15. Adjacent issue (ticket, not this spec)

`RandomTopN` holds `self._rng` as instance state, so its picks depend on call count rather than date.
The causality factory rebuilds per run so truncate-and-compare survives, but the monkey null would
shift if the rebalance schedule ever changed. `default_rng([seed, date.toordinal()])` would make the
null a pure function of the date.
