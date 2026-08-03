# Handoff — Clenow sleeve: ready for implementation planning

**Written:** 2026-08-02
**For:** the session that writes the Clenow implementation plan
**Assumes:** zero context from prior sessions

## Your task

Write the implementation plan for the Clenow momentum sleeve using the
`superpowers:writing-plans` skill. **Do not write code** — the plan is the deliverable.

Source of truth: **`docs/superpowers/specs/2026-07-23-clenow-momentum-sleeve-design.md`**
(status: Approved, both open questions resolved). Read it in full first. It is detailed and
deliberately so — every ambiguity in it was closed after a multi-model review found real defects.

Output goes to `docs/superpowers/plans/YYYY-MM-DD-clenow-momentum-sleeve.md`, matching the format of
the two existing plans in that directory (checkbox tasks, TDD per task, global constraints section).

## Where the project stands

**Phases 0 and 1 are complete and verified in production**, not just merged:

- Nightly data pipeline runs unattended under launchd (`com.number7.nightly`, 22:30 ET). Snapshots
  land daily; current history runs through `data/snapshots/2026-08-01/`. QC green, promotion + external
  heartbeat working. The dead-man alert has fired correctly on a real miss.
- Live Norgate audit passes (`uv run pytest -m vm`).
- Alpaca paper MOC probe has filled on multiple trading days — the Phase-1 execution gate is satisfied.
- Offline suite: 85 tests green, `ruff` clean.

**Phase 2 is the current work.** The Clenow sleeve is its first sub-project; the ETF trend sleeve,
order service, and ops reconciliation are separate specs, later.

## Implementation ordering (from the spec)

Hard sequencing — each stage must be green before the next:

1. **Dual-basis snapshot** (Phase-0 data work). `data/sync.py` pulls `adjustment="capital"` alongside
   total-return; store schema gains `px_*` columns; QC extends schema + OHLC-sanity checks to the new
   basis; snapshot metadata records bases present; re-pull produces a new snapshot id.
2. **`PanelView` extension** to carry both bases. Note the spec requires *renaming* `close` rather than
   duplicating it, so every call site is forced to choose a basis explicitly.
3. **Gauntlet fixes** (§10 of the spec) — walk-forward fold state, monkey matching, closed-loop
   causality check.
4. **Strategy + sizing** — `strategies/clenow.py`, `strategies/sizing.py`.
5. **Calibration** — pre-registrations, runs, memo.

## Decisions already made — do not relitigate

These were settled deliberately, several after review pushback. Rationale is recorded in spec §3, §5,
and §11.

| Decision | Value |
|---|---|
| Ranking basis | Capital-adjusted (price). Clenow ranks price — confirmed against the book. |
| `ann_factor` | **250**, pinned, excluded from the searched parameter space |
| Regime instrument | Capital-adjusted SPY; `$SPX` is a registered variant, not a free swap |
| Strategy contract | **Stateless.** `target_weights(view) -> Slate`; holdings-aware `resolve_book` lives in `sizing.py` |
| Drift band | In the resolver, relative, with mandatory post-band re-validation |
| Marginal name at budget exhaustion | Skipped, not partially filled |
| DSR hurdle | **0.98** (low-N), not 0.95 |
| Reference vs deployable | Two frozen profiles, both gauntlet-run; not a runtime flag |

**One reversal worth knowing about:** an earlier draft made the strategy holdings-aware
(`target_weights(view, current)`). That was reversed. The justification had been that a strategy needs
holdings to re-size retained names — which is false: ATR-parity weights are per-name and
set-independent, so emitting weights for all *eligible* names already covers retained ones. Three
independent reviewers rejected holdings-in-strategy; the `Slate` return type gets the same semantics
while keeping the causality proof total. Do not reintroduce holdings into the strategy signature.

## Defects confirmed in existing Phase-1 code (in scope, plan must cover)

Each was verified against the actual source, not merely asserted by a reviewer:

1. **SPY is a buyable candidate.** `engine/live.py:22-23` sets `in_index = True` for all
   `extra_symbols`, so the momentum book would hold its own regime instrument, and it pollutes the
   `hold_top_pct` denominator.
2. **Walk-forward folds start flat.** `validation/walkforward.py` builds a fresh strategy per fold and
   `run_backtest` starts in cash. An OOS fold opening in regime-off can never buy → ~0 return → biases
   WFE against bear folds.
3. **Monkey null is mismatched.** `validation/monkey.py` uses `RandomTopN`, which is always fully
   invested and equal-weight, against a candidate that is often part-cash and ATR-sized.
4. **Drift band can breach `position_cap` silently.** `engine/strategy.py::validate_weights` checks
   finite/≥0/sum≤1 only — not `position_cap`. The band runs after normalization, so a name retained at
   0.104 against a 0.10 cap passes undetected, and gross can exceed 1.0.

These are only discoverable *because* of this strategy; fixing them is part of this work, not a
separate hardening pass.

## Traps specific to this repo

- `set -o pipefail` when piping pytest to `tail`/`grep` — a bare pipe swallows the exit code.
- Tests never touch the network except the `vm` and `paper` marks, which are deselected by default.
- Snapshots are immutable and versioned because Norgate back-adjusts history. Research runs pin a
  snapshot id. The dual-basis change therefore produces a **new** snapshot, not an edit.
- `ops/com.number7.nightly.plist` hard-codes machine paths **by design** (documented in its header).
  Copilot review flags it repeatedly; do not "fix" it.
- `execution/lots.py` wash-sale chaining semantics were settled across review rounds 17→20 — read those
  commits before touching it.
- The walk-forward WFE is deliberately ratio-of-means with an IS-profit floor. Read the docstring before
  "fixing" it.
- Both launchd units exec uv via the **mise shim** (`~/.local/share/mise/shims/uv`); `/opt/homebrew/bin/uv`
  does not exist on this machine and silently kills the job with status 78.

## Parked — not part of this plan

- **Risk constitution §8 tuning.** The blueprint says draft numbers should be tuned before Phase 2.
  Still outstanding, owner Viktor. Does not block the plan; does block real capital.
- **Paper probe accumulation.** `com.number7.paper` still buys 1 SPY every trading day into the paper
  account (~5+ shares held). Its gate purpose is served; it should be unloaded and the position
  flattened before Phase-2 reconciliation starts, or it will muddy live-vs-sim.
- **`RandomTopN` RNG is call-count dependent**, not date-dependent (spec §15). Ticket, not this plan.
- Portfolio risk layer (vol-target scalar, sector caps, loss brakes, liquidity overlay) — deferred by
  design to its own spec, but the plan must include the **hard guard refusing non-paper mode while
  `risk_layer_version is None`**.

## Git state

`main` at `afa8bb0`, clean. Local commits ahead of `origin/main` are **not pushed** — push was not
requested. `AGENTS.md` and `resume` are untracked and predate this work; leave them alone.
