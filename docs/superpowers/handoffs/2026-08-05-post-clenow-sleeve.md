# Handoff — Clenow sleeve shipped; what comes next

**Written:** 2026-08-05
**For:** the next session
**Assumes:** zero context from prior sessions

## Read this first

**The nightly data pipeline has been dead since 2026-07-23 and `data/current` is stale.**
Everything below is secondary to that. See "Operational state" — it needs fixing before any
research or trading work means anything.

## What just shipped

PR #2 merged (`b587dd6`): the Clenow momentum sleeve, the first Phase-2 sub-project. 27
commits, 175 tests (baseline was 85), `ruff` clean.

Source of truth remains `docs/platform-blueprint.md`. The sleeve's design spec is
`docs/superpowers/specs/2026-07-23-clenow-momentum-sleeve-design.md` and its executed plan is
`docs/superpowers/plans/2026-08-02-clenow-momentum-sleeve.md`. **The plan text is NOT
authoritative where it disagrees with the code** — seven of its twelve tasks found genuine
defects in its own literal code or tests, and the code won each time. Read the code.

What exists now that did not before:

- **Dual-basis snapshots.** `sync.py` pulls `adjustment="capital"` alongside total-return.
  Schema is `px_*` (signals) / `tr_*` (P&L) / `raw_close` (fills, ADV, reconciliation). Basis
  assignment is normative — mixing bases is a silent correctness bug, and the whole reason the
  old `close` field was *renamed* rather than duplicated was to force every call site to choose.
- **`strategies/clenow.py`** — stateless `target_weights(view) -> Slate`, a pure function of
  the panel. Do not add holdings to it; that purity is what makes truncate-and-compare a
  *total* causality proof rather than a pointwise one.
- **`strategies/sizing.py`** — the holdings-aware resolver (admission, budgeted fill, cap,
  normalization, floor, drift band), shared verbatim with the future ETF sleeve.
- **Three gauntlet fixes**: walk-forward folds carry IS end-state; the monkey null is matched
  to the candidate; causality is checked closed-loop as well as pointwise.
- **A trading gate**: `Settings` refuses non-paper mode while `risk_layer_version is None`.

## Operational state — needs attention first

| thing | state |
|---|---|
| Nightly pipeline | **dead since 2026-07-23** — snapshots `2026-07-23`…`2026-08-02` are empty dirs |
| Last good production snapshot | **2026-07-22** |
| `data/current` | still points at 2026-07-22, **pre-dual-basis schema** |
| Dead-man alert | **11+ missed heartbeats did not reach Viktor** — the alert path itself is suspect |
| Norgate bridge | healthy as of 2026-08-04 (`pytest -m vm` green) |

Two separate problems. The pull failures matter less than the alert silence: a pipeline that
fails is expected, a pipeline that fails *silently for eleven nights* is the actual defect.
Diagnose the heartbeat path before trusting any future green run.

**`data/current` must be promoted to a dual-basis snapshot before anything reads it.** The
merged code cannot read the old schema — `build_panel` raises `MissingBasisError` by design, so
a snapshot lacking the price basis is detectably unusable rather than silently mis-ranked. Run
`uv run python -m number7.ops.nightly` on a trading day and confirm `meta.bases` lists both
bases. A verified dual-basis snapshot exists at scratch path from the 2026-08-04 gate run if
you want a reference, but production needs its own.

## What the calibration found, and what it implies for sequencing

Full gauntlet, 16h, `n_monkeys=1000`, snapshot 2026-08-04. Memo:
`docs/research/2026-08-clenow-calibration-memo.md`. Deployable profile: $50k → $352,551 over
22.5 years (9.05% CAGR, Sharpe 0.55, max DD −27.8%, beta 0.50, 78% average gross).

Four of five gates pass. **The monkey test fails its drawdown leg**, and this is the finding
that should drive sequencing:

> The strategy out-earned *every one* of 1,000 rank-shuffled matched nulls (profit percentile
> 1.000) while drawing down deeper than 99.9% of them (0.001). Momentum ranking carries real
> return information **and** concentrates the book into names that fall together.

That is a direct empirical measurement of the common-factor exposure the deferred portfolio
risk layer exists to control — previously only an argument (25 positions at 10bp each imply
~8% annualized vol if independent, ~23% at 0.30 average pairwise correlation). It is no longer
an argument. **The risk layer is the highest-value next piece of work**, and the guard in
`config.py` already refuses live mode until it exists.

Also recorded, deliberately **not** acted on: the gap filter fails its ablation on Sharpe,
exposure-adjusted return and drawdown simultaneously. Investigated rather than assumed — our
overnight definition is the *conservative* of the source's two readings, vendor artifacts are
rare (4.7% of trips), but each trip disqualifies a name for 90 sessions, blocking 3.5% of
constituent-days normally and 8–10% in 2008/2009/2020. Changing it would be exactly the
parameter-nudging §11.4 forbids and would spawn a new pre-registration and a new trial. If a
searched variant ever addresses it, that must be a declared, registered decision.

## Suggested order of work

1. **Fix the nightly + heartbeat**, promote a dual-basis snapshot. Nothing else is meaningful
   until `data/current` is fresh and failures are visible.
2. **Portfolio risk-layer spec** — vol-target scalar and anti-procyclicality clause, sector cap
   and top-3 concentration (needs GICS threaded into the panel), loss brakes, liquidity overlay
   (ADV cap, Corwin-Schultz spread gate, beta band). The monkey result is your motivating
   evidence. Brake thresholds come from this run's bootstrap drawdown distribution: 95th
   −49.5%, 99th −57.7%.
3. **Order service** — `compute_live_targets` is already the exact entry point it must call.
   Read §8.4 of the sleeve spec before building `current`: it is broker share counts × the
   signal date's official close ÷ sleeve equity, **never** broker market value.
4. ETF trend sleeve, ops reconciliation — separate specs, later.

Before real capital, in this order: build production profile → estimate MC thresholds → freeze
→ **re-run the full gauntlet on the production profile** → then capital. The profile pair in
the memo is a declared diagnostic, not deployable evidence.

## Decisions already made — do not relitigate

| decision | value |
|---|---|
| Ranking basis | capital-adjusted price (`px_close`), confirmed against the book |
| `ann_factor` | 250, pinned, excluded from the searched space |
| ATR | Wilder smoothing, mean seed, `atr_window × 5` burn-in |
| Regime instrument | capital-adjusted SPY; `$SPX` is a registered variant, not a free swap |
| Strategy contract | stateless `target_weights(view) -> Slate`; holdings live in `sizing.py` |
| Budgeted fill | terminates at the marginal name; bounded by full equity (1.0), not `gross_max` |
| Floor | single pass, shortfall to cash |
| DSR hurdle | 0.98 |
| Trial counting | `family_trials` counts **distinct `param_hash`**, not raw run rows |
| Gap definition | overnight `\|open/prev_close − 1\|` |

## Traps

- **`summary()` now requires `BacktestResult.initial`.** Its CAGR is normalized by starting
  capital. The old version exponentiated the equity *level*, so any run with `initial != 1.0`
  reported nonsense (the first calibration claimed 76% where the truth was 9.05%). If you add
  a new `BacktestResult` construction site, populate `initial`.
- **`ruff` now enforces `E501`.** It previously did not — `line-length = 100` was set but no
  `lint.select`, so the default rule set excluded it. "ruff clean" means more than it used to.
- **`Settings.model_copy(update=...)` and `model_construct()` bypass the trading gate.** Both
  skip validation by pydantic v2 design and cannot be closed. Direct attribute assignment *is*
  closed via `validate_assignment=True`. Documented in `config.py` where you will meet it;
  never build a trading process's runtime config through either.
- `ops/com.number7.nightly.plist` hard-codes machine paths **by design**. Copilot flags it
  every time. Do not "fix" it.
- `execution/lots.py` wash-sale chaining was settled across review rounds 17→20. Read those
  commits first.
- The walk-forward WFE is deliberately ratio-of-means with an IS-profit floor. Read the
  docstring before "fixing" it.
- Both launchd units exec uv via the **mise shim** (`~/.local/share/mise/shims/uv`);
  `/opt/homebrew/bin/uv` does not exist here and silently kills the job with status 78.
- Tests never touch the network except the `vm` and `paper` marks, deselected by default.
- Chain test commands with `set -o pipefail` when piping to `tail`/`grep`.

## Parked

- **§8 risk-constitution tuning** — draft numbers still untuned. Owner Viktor. Blocks capital.
- **Paper probe accumulation** — `com.number7.paper` buys 1 SPY every trading day into the
  paper account. Its gate purpose is served; unload it and flatten before Phase-2
  reconciliation, or it will muddy live-vs-sim.
- **`RandomTopN` RNG is call-count dependent**, not date-dependent. Ticketed, not urgent —
  `ClenowMomentum(shuffle_seed=·)` uses the correct `(seed, date)` construction, so the matched
  monkey null does not inherit the bug.
- **`var_of_trial_sharpes` vs `expected_max_sr`** — now deduped by `param_hash` like
  `family_trials`. No action, noted for symmetry.
- Ledger rows from the first calibration run carry the uncorrected `cagr`. Superseded by the
  memo; not worth rewriting history over.

## Git state

`main` at `b587dd6` (merge of PR #2), pushed. 175 tests green, `ruff` clean.

**One cleanup for Viktor:** local `main` in the primary checkout has three unpushed docs
commits (`ddfe64d`, `afa8bb0`, `9553632`) whose content was cherry-picked into the merged
branch. Verified byte-identical by `git patch-id`. Discard them rather than pushing:

```bash
git -C /Users/vyarmak/Developer/projects/ai/trading/number7 fetch origin
git -C /Users/vyarmak/Developer/projects/ai/trading/number7 reset --hard origin/main
```

The `phase2-clenow-sleeve` branch and its worktree still exist; both can be removed once you
are satisfied with the merge.
