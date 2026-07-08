# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Personal autonomous trading platform (EOD US equities/ETFs, ~$50k, weekly MOC rebalancing).
**`docs/platform-blueprint.md` is the design source of truth** — architecture, validation
gauntlet (§6), risk constitution (§8), and the multi-LLM review record (§14) live there.
Implementation plans (executed, kept for provenance) are in `docs/superpowers/plans/`.
The 68-book knowledge base in `knowledge-base/` (cited as KB-NN) grounds every design rule.

Status: Phases 0 (data spine) + 1 (validation harness) merged. Phase 2 (baseline book on
Alpaca paper) is next; its manual gates are in the PR #1 test plan.

## Commands

```bash
uv sync                                   # Python >= 3.13; norgate-bridge is a rev-pinned git dep
uv run pytest                             # default run: vm/paper markers deselected
uv run pytest tests/test_backtest.py -v   # one file
uv run pytest -k wash_sales -v            # one test by keyword
uv run pytest -m vm                       # LIVE Norgate bridge audit (needs .env + reachable VM)
uv run pytest -m paper                    # Alpaca paper MOC probe (trading day, before 15:45 ET)
uv run ruff check src tests
uv run python -m number7.ops.nightly      # full nightly: sync -> QC -> promote -> prune
uv run python -m number7.data.audit       # Norgate delisting/split/total-return audit (live)
```

Always chain test commands with `set -o pipefail` when piping to `tail`/`grep` — a plain
pipe swallows pytest's exit code (this bit us once).

## Architecture (the parts that span multiple files)

**Data flow:** `norgate-service` REST bridge (separate repo, runs on the Windows VM with
Norgate Data Updater) → `data/sync.py` pulls the "S&P 500 Current & Past" universe + SPY →
immutable snapshot at `data/snapshots/<db_date>/` → `data/qc.py` (8 checks) gates promotion →
`data/current` symlink. **Snapshots are immutable and versioned because Norgate back-adjusts
history**; research runs pin a snapshot id for reproducibility. QC failure ⇒ no promotion AND
no heartbeat ping ⇒ the external dead-man alert fires (`ops/nightly.py`).

**The timing contract (§4.1, normative everywhere):** weights executed at the close of
rebalance date T are computed from data ≤ close of T−1. Norgate data lands after T−1's close;
orders submit the morning of T with Alpaca `cls` TIF; fills happen at T's closing auction.
`engine/backtest.py` enforces this by masking (`PanelView.masked_to(signal_date(...))`) —
even cost-model inputs (sigma/ADV) use signal-date data. `validation/causality.py`
(truncate-and-compare) proves it per strategy; note its factory takes the panel
(`Callable[[PanelView], Strategy]`) so truncation reaches any state a strategy precomputes.

**Backtest = live parity:** `engine/live.py::compute_live_targets()` is the exact function
the Phase-2 order service will call. `tests/test_live_parity.py` (golden replay) pins
engine-decided weights ≡ live-path weights. Any engine change must keep that test green.

**Strategy contract:** strategies emit long-only, unlevered weights (`validate_weights` —
finite, ≥ 0, sum ≤ 1; cash is the remainder) via `target_weights(view)`. `RandomTopN` is the
null/calibration fixture (and the monkey-test engine); `LookaheadTrap` exists to be caught.

**Anti-overfitting machinery** (`research/` + `validation/`): every backtest logs to the
DuckDB trials ledger; `PreRegistration` (machine-readable hypothesis) must precede runs;
scrapped param spaces cannot re-register (`param_hash` normalizes list order — don't weaken);
DSR hurdles are origin-tiered (LLM-proposed families and low-N get 0.98, not 0.95). The
walk-forward WFE is deliberately ratio-of-means with an IS-profit floor — see the docstring
before "fixing" it.

**Determinism:** every stochastic component takes an explicit seed. Tests never touch the
network except the `vm`/`paper` marked ones.

## Non-obvious constraints

- `ops/com.number7.nightly.plist` hard-codes this Mac's paths **by design** (documented in
  its header; VPS uses the systemd units). Copilot review repeatedly flags it; the decline
  rationale is recorded in blueprint §14 and commit history — don't "fix" it.
- `execution/lots.py` wash-sale logic is a detection aid for the tax clause (§8), not tax
  filing software; its chaining semantics were deliberately settled in review rounds 17→20
  (see commit messages) — read those before changing the rules.
- The bridge VM is trading-critical: stale `X-Norgate-Db-Date` / failed health check must
  always degrade to "hold state, no trades", never to trading on stale data.
- Symbols legitimately return zero bars (delisted before `history_start`); only
  `extra_symbols` (SPY) are hard-required (`sync.py`), and QC's orphan check only covers
  membership stints overlapping the pulled range.
