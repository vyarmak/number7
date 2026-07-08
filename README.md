# number7

Personal systematic trading platform: EOD US equities/ETFs, weekly market-on-close
rebalancing, with an LLM-driven research loop planned on top of a statistics-first
validation harness. Single-user infrastructure — not a product, not financial advice.

**Design source of truth:** [`docs/platform-blueprint.md`](docs/platform-blueprint.md) —
feasibility verdict, architecture, validation gauntlet, risk constitution, phased roadmap,
and the multi-LLM review record. Grounded in the 68-book knowledge base under
[`knowledge-base/`](knowledge-base/).

## Status

| Phase | Scope | State |
|---|---|---|
| 0 | Data spine: Norgate bridge sync → immutable QC-gated snapshots (Parquet/DuckDB) | ✅ merged |
| 1 | Validation harness: causal backtest engine, cost model, walk-forward, PSR/DSR, trials ledger, monkey/Monte-Carlo tests, golden-replay parity, lot/wash-sale accounting | ✅ merged |
| 2 | Baseline book (Clenow momentum + ETF trend) → Alpaca paper | next |
| 3 | LLM research loop (pre-registration → gauntlet → human-gated promotion) | planned |
| 4 | Live capital, concave ramp | planned |

## Layout

```
src/number7/
├── data/         # bridge client glue, snapshot sync, QC gate, PIT universe, DuckDB catalog
├── engine/       # causal backtest engine, schedule, cost model, live-target contract
├── validation/   # causality harness, PSR/DSR, walk-forward, monkey test, bootstrap bands
├── research/     # pre-registration schema + trials ledger (anti-overfitting spine)
├── execution/    # FIFO lots + wash-sale detection
├── brokers/      # Alpaca paper MOC probe
└── ops/          # nightly orchestrator, snapshot retention
ops/              # launchd (research Mac) + systemd (execution VPS) units
docs/             # blueprint + implementation plans
knowledge-base/   # distilled trading literature (KB-NN citations)
```

## Quickstart

Requires Python ≥ 3.13, [uv](https://docs.astral.sh/uv/), SSH access to the private
`norgate-service` repo, and a reachable Norgate bridge (Windows VM running Norgate Data
Updater + the REST bridge).

```bash
uv sync
cp .env.example .env          # bridge URL/token, data dir, heartbeat URL, Alpaca paper keys
uv run pytest                 # offline suite (80 tests; vm/paper markers excluded)
uv run python -m number7.ops.nightly    # build, QC, and promote a real snapshot
uv run pytest -m vm           # live Norgate audit: splits, delisted names, total return
uv run pytest -m paper        # Alpaca paper MOC probe (trading day, before 15:45 ET)
```

Nightly scheduling: `ops/com.number7.nightly.plist` (this Mac, paths machine-specific by
design) or `ops/number7-nightly.{service,timer}` (VPS, `/opt/number7` layout).

## Design principles (short version)

- **LLM proposes, pipeline disposes** — no model in the order path, ever.
- **Timing contract:** decisions use data through T−1's close; fills at T's closing auction.
  Enforced by masking, proven by truncate-and-compare, pinned by a golden-replay parity test.
- **The trials ledger is the crown jewel:** hypotheses are pre-registered before any
  backtest, every run is logged, deflated-Sharpe hurdles scale with the search, and scrapped
  parameter spaces cannot quietly re-enter.
- **Snapshots are immutable** — Norgate restates history; research pins snapshot ids.
- **QC failure = no promotion = dead-man alert.** Silence is never success.
