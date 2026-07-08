# Number7 — Autonomous Trading Platform: Research & Recommendations

*Prepared 2026-07-07. Inputs: the 68-book knowledge base in `knowledge-base/` (cited as KB-NN), plus a multi-source web research pass (cited in §12). This is a design/feasibility study, not financial advice.*

---

## 1. Verdict up front

**Feasible — with one critical reframing.** "An autonomous, self-improving trading system" is actually three different systems, and they have very different feasibility:

| Claim | Feasibility | Comment |
|---|---|---|
| **A. Autonomous execution** of systematic EOD strategies (signals → orders → risk checks → monitoring, unattended) | **Solved problem.** | Well-trodden retail-quant territory. Your experience + hardware + Alpaca/IBKR make this straightforward. |
| **B. LLM-automated research factory** — agent proposes strategy variants, implements them in branches, backtests, validates, writes memos; human gates promotion | **Feasible and genuinely valuable.** This is where your specific combination of assets (30 yrs engineering, Claude Code, a machine-readable knowledge base, strong hardware) is an actual edge. | The bottleneck is *statistical validation*, not code generation. The design must be built around a trials budget (§6), or the loop automates self-deception at scale. |
| **C. LLM making trading decisions at trade time** ("the AI trades") | **Not recommended as the core — now with hard evidence, not just caution.** Keep the LLM out of the order path entirely. | The 2025–26 replication literature is brutal (§12.1): in the largest independent test (FINSABER, 20 years, S&P 500 incl. delisted, peer-reviewed KDD 2026), FinMem and FinAgent show **no statistically significant alpha** (all p > 0.34); across five major agent systems, Sharpe decays **51–62%** once the test window passes the LLM's pretraining cutoff; memorization audits show GPT-4o-class models recall historical financial facts at **85–93%** accuracy — the agents were reciting remembered history, not predicting. **Zero documented real-money results across all six major systems.** |

**Recommendation: build A as the chassis, B as the engine of improvement, and explicitly do not build C.** The LLM proposes; a deterministic pipeline disposes.

**Expectation setting (important).** Your knowledge base itself gives the honest numbers: the realistic *ceiling* for a well-diversified retail systematic book is Sharpe ≈ 1.0, and live Sharpe ≈ ½ of backtest (Carver, Chan; KB-07). At $50k with a 10–12% volatility target, a good outcome is roughly **$4–7k/year expected return with 15–25% drawdowns along the way**, i.e. this project's near-term payoff is measured in learning, infrastructure, and optionality (it scales if it works), not income. Aronson's 6,402-rule study found *zero* surviving edges after data-mining correction (KB-07 §4a) — treat that as the prior the system must overcome. If that expectation is acceptable, everything below is worth building. If the goal is income replacement from $50k, no architecture fixes that math.

---

## 2. Assumptions (explicit, per your rules)

1. **Asset class & frequency:** US equities/ETFs, end-of-day bars, holding days-to-months. Forced by Norgate (EOD data) and supported by the KB's equities/ETF weighting. Intraday/HFT is out of scope (different data, infra, and edge-decay regime — KB-11 §11 says redirect that budget to data quality and reconciliation).
2. **Capital:** ~$50k, taxable account, no leverage initially. PDT rule ($25k threshold) is satisfied anyway but EOD cadence makes it moot.
3. **Time budget:** you can invest focused part-time effort over ~3–4 months to reach a live-capital-ready system. Phases in §10 are sized in focused weeks; stretch accordingly.
4. **Autonomy target:** autonomous *process*, human-gated *capital decisions* — at least for the first year. The trust ladder (§8) widens autonomy with track record.
5. **The Mac is the research machine; execution reliability is solved separately** (§9). "Never deploy from your local machine" (Hilpisch, KB-11 §7) is softened for an EOD system but not ignored.
6. **Options, futures, ML price-prediction models: deferred.** Adjacent expansions after the core proves itself (§10 Phase 5). The KB is explicit that DL/ML doesn't rescue weak signals (ICs 0.01–0.03, fragile; KB-06) and that a clean classical baseline must exist first (KB-00 build path).

If any assumption is wrong — especially #1 (asset class) or #4 (how much capital autonomy you actually want) — say so; it changes the design more than any tooling choice.

---

## 3. The strategic frame: what your edge actually is

A solo retail trader has no edge in speed, information, or breadth against institutions. The realistic edges available to you, in order of reliability:

1. **Discipline encoded in software** — the system takes every qualifying signal, sizes positions by rule, and never revenge-trades (KB-12). This is the most durable edge and costs only engineering.
2. **Harvesting documented risk premia** — cross-sectional momentum, trend, value/quality tilts, short-term mean reversion (KB-02, KB-04). Small, statistical, decaying — but real, and available at retail capacity precisely because they're too small for institutions to bother at your scale.
3. **A research factory with lower cost-per-hypothesis than any human team** — this is the new part. Claude Code + your validation harness can take a hypothesis from idea to fully-validated verdict for a few dollars of compute. Davey needed 100–200 ideas per tradable system (KB-07 §1); making each idea cheap *and statistically honest* is the whole game.
4. **The knowledge base as machine-readable priors.** López de Prado's precision argument (KB-07 §4a): a backtest's believability depends on the prior odds that the hypothesis is real. An agent that generates hypotheses *grounded in the KB's documented premia and mechanisms* — instead of free-form mining — raises those priors and directly lowers the false-discovery rate. Almost nobody's retail loop has this. Yours does.

The anti-edge to respect: **an automated research loop is an automated multiple-testing machine.** 1,000 zero-edge trials manufacture an expected max Sharpe of 3.26 (KB-07 §4a). The design answer is the trials ledger + deflated Sharpe gate (§6), and a hypothesis generator that is deliberately *frugal and theory-first*, not generative-spam.

---

## 4. System architecture

### 4.1 The spine

Narang's five modules over data + research layers (KB-11 §1), with the LLM layer strictly *outside* the trade path:

```
                        ┌──────────────────────────────────────────────┐
                        │            AGENT LAYER (LLMs)                │
                        │  hypothesis gen · implementation · memos ·   │
                        │  post-trade analysis · monitoring triage     │
                        │  — writes code & reports, NEVER orders —     │
                        └───────────────┬──────────────────────────────┘
                                        │ PRs / memos / configs (human-gated)
        ────────────────────────────────┼────────────────────────────────
                                        ▼
   ┌────────────┐   ┌────────────┐   ┌─────────────────┐
   │ Alpha      │   │ Risk       │   │ Transaction-cost │      DETERMINISTIC
   │ (strategies)│  │ (limits)   │   │ model            │      TRADE PATH
   └─────┬──────┘   └─────┬──────┘   └────────┬────────┘
         └────────────────┴───────────────────┘
                          ▼
              ┌───────────────────────┐     target − current = trades
              │ Portfolio construction │ ──────────────┐
              └───────────────────────┘                ▼
                                            ┌─────────────────────┐
                                            │ Execution + broker  │
                                            │ adapter + reconcile │
                                            └─────────────────────┘
   UNDERNEATH: data layer (Norgate ETL → Parquet/DuckDB) + research layer (backtest engine,
   validation harness, trials ledger, experiment registry)
```

Design rules carried over from the KB, each of which prevents a documented failure mode:

- **Diff-based control loop.** Portfolio construction emits a *target portfolio*; the system diffs against current positions and the differences are the trades (Narang, KB-11 §1). No "signal firing" spaghetti.
- **Backtest = live at the signal → target → diff layer, proven by tests — not claimed.** One codebase computes signals, targets, and trade diffs in both modes (Chan/Halls-Moore/Aldridge, KB-11 §3–4); fills and frictions differ by construction (simulated vs. auction reality), so parity is *verified*, not assumed: a **golden-replay CI test** feeds identical inputs through the research path and the live dry-run path and requires identical target portfolios, orders, cash, and blocked-trade decisions (multi-LLM review, §14). Empirical fill quality closes the loop: promotion depends on measured live slippage staying inside the cost model's bands.
- **Explicit timing contract (the sharpest review consensus, §14).** Norgate EOD data lands *after* the close of day T−1; therefore: signals compute overnight from T−1 closes → orders submit morning of T with `cls` TIF → fills occur at **T's closing auction** — and the backtest models exactly that (signal close T−1, fill close T). Every strategy manifest declares its four timestamps (signal, decision, order-cutoff, fill); the harness rejects any strategy that can't prove the ordering. A hard data-freshness cutoff governs the morning submit: bridge `X-Norgate-Db-Date` ≠ T−1 ⇒ no orders, alert, carry last targets.
- **Two-cadence scheduler** (Clenow, KB-11 §9a): a *daily compute pass* (features, rankings, regime state — always runs) feeding a *weekly trade day* (sell → rebalance → buy, with a 5% drift band and a regime gate as throttles). Roster changes and position resizing are separate triggers. Daily granularity in the engine even though you act weekly.
- **Position inertia everywhere** (Carver, KB-11 §1a): don't trade unless the target is >~10% away from current (or outside Clenow's 5% band). Turnover is the tax you control.
- **Standardized strategy interface** (Carver): every strategy emits a normalized forecast; adding a strategy = adding a forecast + a weight. This is what makes the research factory composable — the agent authors new modules against a fixed contract.
- **Separate counters for orders-sent vs. fills, reconciled every cycle** (Aldridge, KB-11 §11) — the anti-runaway rule. Plus positions reconciled against broker truth after every trade day; mismatch ⇒ freeze + alert.
- **Panic button & kill-switch criteria decided in advance** (Narang/Douglas, KB-11): documented triggers, not vibes. The biggest un-engineered risk is the operator overriding the system mid-drawdown (Carver: don't fully automate until you trust it enough not to shut it off).

### 4.2 Proposed repository layout

```
number7/
├── data/            # ETL from Norgate → Parquet + DuckDB; QC suite; universe & constituent tables
├── engine/          # event-driven core shared by backtest and live (framework glue lives here)
├── strategies/      # one module per strategy + manifest.yaml (hypothesis, params, universe, status)
├── portfolio/       # vol targeting, allocation, diff-to-trades
├── risk/            # constitution.yaml (hard limits), risk overlay, kill-switch  ← agent-read-only
├── execution/       # broker adapters (Alpaca first), order state machine, reconciliation
├── research/        # validation harness, trials ledger, experiment registry, hypothesis backlog
├── agents/          # Claude Code job definitions, prompt templates, memo formats
├── ops/             # schedulers (launchd/cron), monitoring, alerting, dashboards
├── knowledge-base/  # existing KB + living memory: post-trade learnings appended over time
└── docs/            # this document, research memos, IPS/constitution rationale
```

### 4.3 Where each LLM goes (division of labor)

| Role | Model | Why |
|---|---|---|
| Research loop: hypothesis drafting, strategy implementation, gauntlet orchestration, research memos, post-trade retros | **Claude Code (frontier, API/subscription)** | Highest-stakes reasoning and code quality; runs headless on schedule (§7). |
| Second-opinion review of any PR touching `execution/`, `risk/`, `portfolio/` | **Codex / Antigravity** (and/or Gemini via your existing tooling) | Multi-model review catches single-model blind spots. Cheap insurance on the money path. You already have the harness for this. |
| Bulk/cheap tasks: log & QC-report triage, first-pass idea screening against the KB, summarizing fills/slippage reports, (later) news/sentiment tagging | **Local model via oMLX on the M5 Max** | Zero marginal cost, private, always-on. 128GB comfortably serves a large quantized model (verified in §12). Not for final research judgment. |
| Nothing | **Any LLM at trade time** | See §1, claim C. The order path is deterministic Python. |

A practical note from the LLM-agent literature (KB-06): ATLAS's "reflection paradox" — naive periodic self-reflection often *degrades* strong agents. When you build the agent's self-analysis jobs, make them **windowed, evidence-anchored, and schema-constrained** (structured memo templates with metrics attached), not free-form "reflect on your performance" prompts.

---

## 5. The self-improvement loop (the crown jewel — design it around statistics, not around the LLM)

The loop is the scientific method, automated, with the trial count as a first-class managed resource:

```
        KB + literature + live-trading observations
                        │
                        ▼
 1. HYPOTHESIS (pre-registered)          agent drafts; template forces:
    premise & mechanism · KB/paper citation (prior odds!)
    expected effect & falsification criteria · parameter ranges
    planned trial count                   ← logged to trials ledger BEFORE any backtest
                        │
                        ▼
 2. IMPLEMENT           agent codes strategy module in a git branch,
                        against the fixed strategy interface; unit tests; CI runs
                        look-ahead audit (truncate-and-compare) automatically
                        │
                        ▼
 3. GAUNTLET (deterministic harness, §6)  every run auto-logged with
                        code hash · data snapshot hash · params · full metrics
                        │
                        ▼
 4. MEMO + VERDICT      agent writes research memo: metrics vs. gates,
                        sensitivity plots, DSR given ledger count, recommendation
                        │
                        ▼
 5. HUMAN GATE          you review PR + memo (~15–30 min). Merge ⇒ paper.
                        │
                        ▼
 6. PAPER INCUBATION    3–6 months (absolute floor 8 weeks) or ≥30 trades;
                        daily live-vs-sim reconciliation within bands; auto-demote on breach
                        │
                        ▼
 7. CAPITAL RAMP        concave allocation: ~5% → 25% → full sleeve target
                        (de Prado lifecycle: embargo → paper → graduation →
                        re-allocation → decommission)
                        │
                        ▼
 8. LIVE MONITORING     efficiency ratios, live-vs-sim divergence, monkey-test
    & RETIREMENT        re-runs every 6 months; decay ⇒ taper ⇒ decommission.
                        Learnings appended to knowledge-base/ (self-education).
```

Design decisions that make this loop honest rather than a curve-fitting machine:

1. **Pre-registration before backtest — as a machine-readable schema, not free text** (kills HARKing; review consensus §14: prompt obedience is not a control). The hypothesis is a structured document: premise/mechanism, KB/paper citation, expected effect size, falsification criteria, and the **exact parameter ranges** — committed before the first backtest, and the harness *enforces* those parameters (a run outside the registered range is rejected by code, not by convention). Kaufman: "the computer validates a belief, it must not create one" (KB-07 §1).
2. **Trials ledger with anti-gaming teeth** (SQLite/DuckDB). Every backtest run by anyone — agent or you — increments the ledger with config hash, data-snapshot hash, and result. Three enforcement mechanisms the review demanded (§14): (a) **semantic/parameter-cluster dedup** — new pre-registrations are checked against failed lineage; a rephrased variant of a scrapped idea is auto-rejected and can re-enter only with human sign-off; (b) **family-scoped trial accounting** — early on (ledger too small for ONC clustering, which needs a cross-trial correlation matrix), the DSR hurdle uses the *declared search-space size* per family (Aronson-style explicit counting); ONC-clustered effective counts take over once the ledger holds enough return series (KB-07 §4a); (c) the quarterly **trial budget** is enforced at the orchestrator level (hard caps), not by the agent's good behavior. One deliberate conservatism for LLM-generated hypotheses: their true prior trial count includes the community's published mining (which the model has read) — so LLM-originated families carry a **stricter DSR hurdle tier** than human-originated theory-first ones.
3. **Variation factory over free-form invention** (Davey, KB-11 §9): the agent's default job is to vary *one axis at a time* of an already-validated base system (universe, cadence, entry, exit, filter) — a bounded search with high prior odds — and to check that the variant is *diversifying* (daily-return correlation, combined MC drawdown) before proposing it. Free-form novel strategies are allowed but rationed: they must cite a KB mechanism or a published paper (raising θ), and they draw down the trial budget faster.
4. **Data segmentation with a single-use vault — anchored to the LLM's knowledge cutoff.** ~60% in-sample / 20% validation / 20% final OOS (Kaufman, KB-07 §3), plus an **embargoed vault** the harness opens once per candidate at promotion. Review consensus (§14): a vault period the proposing LLM has *read in pretraining* is partially compromised regardless of harness locks — so the vault window **starts at the proposing model's knowledge cutoff** and rolls forward with time; paper trading (data no model has seen) carries the most evidentiary weight, the vault is a sanity check, and historical gates are screens — never proof. Vault failure ⇒ family scrapped (no tweak-and-retest); post-promotion, rolling live monitoring (efficiency bands + 6-month monkey re-runs) is the *continuing* OOS, so the single-use vault is not the last line of defense.
5. **Two-tier backtesting for cheap screening.** A vectorized screener (fast, approximate, costs modeled) filters candidates; only survivors get the full event-driven run with realistic fills. This keeps cost-per-hypothesis low without letting the cheap tier make promotion decisions.
6. **The agent never grades its own homework.** The gauntlet is deterministic code with hard numeric gates; the memo *reports* the gates, it doesn't argue with them. A failed gate ⇒ scrap, don't tweak-and-retest (Davey's gates discipline, KB-07 §1) — re-entry requires a new pre-registration and a new ledger entry.
7. **Self-education = structured memory, not vibes.** Post-trade retros, slippage-vs-model reports, regime attribution, and retirement post-mortems get appended to `knowledge-base/` in the same citation-backed format the KB already uses. Over time the system's own live history becomes a source the hypothesis generator can cite — the one dataset nobody else has.
8. **LLM confidence is never evidence.** KB-12's behavioral finding transfers directly: confidence rises with more inputs even when accuracy doesn't. Promotion gates read *metrics*, never the agent's stated conviction; every LLM-proposed rule must be objective, falsifiable, and evaluated point-in-time. Corollary from the same file: a strategy performing *above* its backtest expectation is a warning sign (reversion precursor), not a size-up signal — the monitoring layer treats both tails of the efficiency band as anomalies.
9. **Guard against memorized alpha.** The 2025–26 leakage literature (§12.1) adds a loop-specific hazard: the LLM proposing a strategy has *read the history it will be backtested on* — it can unknowingly encode remembered outcomes ("overweight semis after 2023") as if they were rules. Mitigations, in force from day one: hypotheses must state a *mechanism*, not a pattern ("this works because X risk premium / structural flow", checkable against the KB); parameters must come from the pre-registered range, not tuned-by-narrative; heaviest weight goes to the walk-forward *tail* and paper period — data no model has seen; and any hypothesis that smells like a specific historical episode gets flagged by the reviewer template.

---

## 6. The validation gauntlet (concrete gates, all from your KB)

Every gate is a hard numeric check in code. A candidate advances only by passing; failure means scrap + log.

| # | Gate | Threshold (source) |
|---|---|---|
| 0 | Pre-registration complete | premise + mechanism + KB/paper citation + falsification criteria + planned trials (KB-07 §1, §4a) |
| 1 | Data hygiene | survivorship-free universe with historical index constituents + delisting returns; total-return series; point-in-time everything; signals at close, fills at next open; costs = commission + half-spread + impact; truncate-and-compare look-ahead audit passes in CI (KB-07 §2, checklist) |
| 2 | Sample adequacy | ≥100 trades (prefer ≥400) **and** ≥8 years spanning at least one bear + one bull regime; effective-sample correction for autocorrelated portfolio returns (Newey-West-adjusted Sharpe CIs, block bootstrap for drawdown bands — raw trade counts overstate independence for a weekly book); ≥90% degrees of freedom remaining (KB-07 §3; §14) |
| 3 | Walk-forward | ≥10 rolling windows with pre-frozen protocol per family (window lengths, embargo, objective, rejection rule — frozen *before* testing, so the gate can't be tuned); **WFE ≡ annualized OOS net profit ÷ annualized IS net profit ≥ 50%** (Tomasini/Pardo's "many traders accept ≥50%", KB-07 §3 — an explicit trade-off: we accept up to 2:1 degradation and lean on Carver pessimism factors downstream); stitched OOS curve consistent; parameters from the middle of a robust plateau (KB-07 §3) |
| 4 | Multiple-testing | **DSR > 0.95** against `E[max SR]` (DSR per Bailey–López de Prado: probability true Sharpe > 0 given trials, skew, kurtosis, length — exact formula in KB-07 §4a; *passing = higher is better*); trial count = family-scoped declared search space early, ONC-clustered effective count once the ledger supports it; **low-N tier: effective trials < 15 ⇒ hurdle 0.98**; LLM-originated families use the stricter tier by default; Davey monkey test: beat ~90% of 8,000 random systems **matched on trade count, long/short ratio, and bars-in-trade, holding-period-preserving randomization** (not IID shuffle — must not destroy autocorrelation) on net profit AND max drawdown (KB-07 §4a; §14) |
| 5 | Robustness | Monte Carlo trade-shuffle 99%-confidence drawdown within tolerance; **kurtosis check is family-conditional** — >7 flags overfit for mean-reversion/high-win-rate families (Kaufman's original context), while positively-skewed trend books legitimately run fat-tailed *winners*, so judge trend on skew-adjusted metrics (Sortino) instead; **profit factor sanity range ~1.5–3, with PF > 3 an overfit red flag** (Tomasini: "good systems 1.5–3, >3 is suspicious — re-examine"); price-shock audit (>5×ATR days not driving P&L); survives on sibling instruments/universes; hit ratio > the strategy universe's unconditional positive-share by a binomial-significant margin (KB-07 §3–4; §14) |
| 6 | Economic sanity | net Sharpe ≤ ~2× equal-weight-universe benchmark (else suspect a bug); avg trade comfortably covers slippage+commission; capacity sane vs. ADV (Coqueret & Guida / Tomasini, KB-07) |
| 7 | Vault (single-use final OOS) | opened once, at promotion; performance within pessimism-factor expectations (≈75% of OOS Sharpe; Carver Table 14) |
| 8 | Paper incubation | **Purpose: validates plumbing + cost model, NOT alpha** (12–26 weekly waves have no statistical power on returns — review consensus §14). 3–6 months (floor 8 weeks), go-live trigger fixed *in advance*; numeric reconciliation rule: live-vs-sim daily P&L within ±1σ of simulation on every rolling 10-day window, Kolmogorov–Smirnov on daily P&L distributions, per-instrument divergence audit; measured slippage within the cost model's bands; any breach ⇒ freeze new entries + investigate within 1 business day (KB-07 §6, KB-11 §9, KB-12; §14) |
| 9 | Live ramp & monitoring | concave capital ramp; monthly efficiency ratio 70–100% healthy; live-vs-sim per-instrument divergence = modeling bug ⇒ freeze; monkey-test re-run every 6 months — "when the monkeys catch up, stop trading" (Davey/Clenow/de Prado, KB-11 §9) |

Also encoded once, shared by all gates: Chan's three significance nulls (Gaussian, moment-matched simulation, entry-date randomization — they disagree in instructive ways), and Aronson's detrended/no-skill-baseline correction so position bias × market trend isn't credited as skill (KB-07 §4).

---

## 7. Agent operations (how "mostly autonomous" actually runs)

Scheduled headless jobs (launchd on the Mac; each job = a Claude Code invocation with a fixed prompt template, tools scoped to its directory, and a budget cap):

| Cadence | Job | Autonomy |
|---|---|---|
| Nightly (post-ETL) | Data QC triage: read the deterministic QC report, investigate anomalies, file issues | Full — read-only + issue filing |
| Daily | Compute pass (deterministic, no LLM); optional 5-line book-state note from local model | Full |
| Weekly (trade day) | Execution (deterministic); post-trade memo: fills vs. cost model, slippage, attribution | Full — memo only |
| Weekly–biweekly | Research cycle: pick top backlog hypothesis → pre-register → implement in branch → gauntlet → memo → PR | Autonomous through PR; **human merges** |
| Monthly | Portfolio review: efficiency ratios, correlation drift, decay watchlist, allocation proposal | Proposal only |
| Every 6 months | Monkey-test re-runs on all live strategies; retirement recommendations | Proposal only |
| Quarterly | Deep retro → knowledge-base append; trial-budget reset; process-improvement PR (may touch harness, never constitution) | PR, human merges |

Guardrails that make this safe to run unattended:

- **The constitution is out of reach by OS-level separation, not convention** (review: file perms + branch rules alone are social controls, §14): agent jobs run under a **separate unprivileged macOS user account**; broker keys live in the execution user's keychain (never in the agent user's environment or any repo/env file); GitHub branch protection requires **manual human approval** for merges to main; agent egress is allowlisted (Anthropic/GitHub/local endpoints), and prompt inputs from external text (news, web) are treated as untrusted data, never as instructions.
- **Every agent job has a token/cost budget and a wall-clock timeout — with concrete starting numbers**: data-QC triage ~$1/2min; research-cycle job ~$20/30min end-to-end; monkey-test re-runs ~$10/20min; monthly review ~$5/10min. Tune after the first Phase-3 week; runaway loops die quietly and report.
- **Deterministic gates memo, agent discussion memo — separated** (closes the "agent grades its own homework via narrative" hole, §14): CI generates the *metrics memo* by template-filling directly from gate-result JSON — this is the record of record; the agent writes a separate *discussion draft* (interpretation, next hypotheses); CI cross-checks any gate outcome the discussion claims against the JSON and fails the PR on divergence.
- **Property-based tests on the money path are the gate; multi-model review is advisory** (two providers correctly called mandatory multi-model CI review low-yield for arithmetic/state bugs, §14): `hypothesis`-style property tests on order construction, sizing pipeline, diff-to-trades, plus golden-replay parity, gate every money-path merge; a second-model review pass remains available for design-level diffs at your discretion, not as a blocking gate.
- **Dead-man switches**: stale data ⇒ no trading + alert; missed heartbeat ⇒ alert; reconciliation mismatch ⇒ freeze. Alerts via Telegram/ntfy to your phone.

---

## 8. The risk constitution (draft numbers for $50k — tune before Phase 2)

Hard limits the agent can propose changes to but never merge (IPS-style, per Robbins KB-11 §10):

- **Volatility target:** 10% annualized to start (KB-08: 12% is the futures-fund norm, 6–8% the floor, ≥16% flagged dangerous; Carver's half-Kelly rule `%vol target ≈ ½ × expected Sharpe` says ~10% is consistent with honestly expecting SR ≈ 0.2–0.5 live at first). Raise only after 6 months of live efficiency in band.
- **Position sizing — explicit four-stage pipeline** (review flagged the two sizing layers as ambiguous; order now normative, §14): (1) *relative sizes* via Clenow ATR risk-parity, `shares = (equity × risk_factor) / ATR20`, **risk_factor = 10bp** (KB-08 sweet spot 8–15bp ⇒ ~20–25 positions); (2) *absolute level* via the portfolio vol-target scalar (the 10% target governs; ATR parity only distributes it); (3) *caps* — position, sector, liquidity; (4) *normalization* — if summed targets exceed 100% gross, scale all weights down proportionally (deterministic; the order layer never receives an infeasible book). **Per-position floor $1k** (below ⇒ skip signal — frictions eat it); ATR fault guard: if a name's computed size jumps >2× week-over-week from an ATR spike/gap, hold last size and log a sizing fault. Note: the KB has *no consensus* per-trade risk cap (0.5–1% vs 2% vs ≤5% in the same file); this pipeline is my pick — documented so it's a decision, not a drift.
- **Max single position:** 10% of equity. **Max sector:** 25%. **Max gross exposure:** 100% (no leverage year 1). **No shorting individual stocks, ever** — KB-02: the short leg alone backtested −30% (2000–2014), unbounded risk; KB-07 adds phantom short alpha from borrow/uptick constraints. Index-ETF hedges are the only permitted short instrument, and only post-Phase 5 review.
- **Anti-procyclicality clause:** vol-target de-risking is itself procyclical (a real contagion mechanism in Aug 2007 — KB-08). De-risk on the vol formula but re-risk on a slower clock (asymmetric: fast down, slow up — consistent with KB-13's "up the escalator, down the chute"), and the drawdown brakes below override the formula, not vice versa.
- **Behavioral hard rules in code:** never average down; never increase size during a drawdown; kill thresholds written before go-live and executed mechanically; re-parameterization after a losing stretch is forbidden (KB-08, KB-12 — re-tuning right after losses is explicitly edge-destroying).
- **Order sanity:** per-order notional cap (e.g. $7.5k), ≤0.5–1% of 20-day ADV, price collars, duplicate-order guard, max orders/day. Special-event days (FOMC, witching, reconstitution, month-end) treated as elevated-impact regardless of ADV (KB-01).
- **Loss brakes — two separated families, vol-scaled (redesigned after 3-provider review consensus that fixed thresholds fire on normal noise while contradicting "15–25% DD is normal", §14):**
  - *Malfunction halts (fast, unconditional):* single-day loss > 4× the portfolio's current daily vol estimate, or per-instrument live-vs-sim divergence, or reconciliation mismatch ⇒ stop new orders + page. These catch bugs and gaps, not bad luck.
  - *Performance de-risking (slow, rate-based):* drawdown *rate* — e.g. >1.5× the Monte-Carlo 95th-percentile 10-day drawdown for the current book ⇒ risk halved; crossing the MC 99th-percentile total drawdown (calibrated per book composition, roughly the −20%-HWM region at 10% vol) ⇒ full stop + human review. Thresholds are *derived from the gauntlet's own MC drawdown distributions* at promotion time and recomputed when the book changes — never hand-picked constants.
- **Liquidity & concentration overlay (§14):** position ≤ min(10% equity, 25% of 20-day ADV, notional cap); no new entries in a name whose Corwin-Schultz spread estimate is >2× its rolling median; top-3 holdings combined ≤ 25%; portfolio beta to SPY within a declared band; rolling average pairwise correlation of holdings monitored — sustained spike ⇒ vol-target scalar tightens (the correlation-breakdown brake).
- **Data/ops brakes with a severity ladder (freeze ≠ safety when systems fail mid-crash — §14):** stale or QC-failing data ⇒ hold state, no *new* trades; reconciliation mismatch or broker error spike ⇒ freeze new entries + page immediately; freeze persisting >24h with the malfunction halt also breached ⇒ staged de-risk to cash via the break-glass path (mobile app) rather than blind holding.
- **Override policy (KB-12):** default is **no human override of live strategies** — the natural-experiment evidence is stark (84.1% return for non-overridden automated accounts vs 59.4% for identical accounts with discretionary override). Review closed a loophole (§14): "crisis" is defined as a **pre-specified operational failure** (broker outage, data corruption, desync — resolved by resyncing to broker truth) — **never a P&L event**; P&L responses belong exclusively to the system's own brakes, which the human may *augment* (de-risk further) but not veto. Pre-scheduled event de-risking must be declared before the event, not during it. Everything else goes through the change-control pipeline.
- **Idle cash** parked in a T-bill ETF sleeve (e.g. SGOV-class) rather than broker cash sweep — the regime gate can put the book largely in cash for months; uninvested drag is a real cost at today's rates (Clenow parks excess in government debt, KB-11 §9).
- **Change control:** every strategy promotion/demotion and any constitution change requires your explicit sign-off; the strategy portfolio is culled/admitted on a ~semiannual review cadence (KB-12), not ad hoc. Trust ladder: after 2+ quarters of clean operation, you may delegate promotion-to-paper (§5 loop step 5→6) to the pipeline; capital gates stay human permanently.
- **Counterparty:** start with one broker while small; add the second broker when live allocation exceeds ~$25k (Davey's PFG lesson: spread accounts across brokers; know where each order type is held).

Tax note (not advice) — timing corrected by review (§14): wash-sale handling must be *coded*, not deferred. Same-ticker re-entry within 30 days of a realized loss **is** a wash sale (momentum roster churn does this routinely); the strategy/accounting layer therefore tracks per-lot cost basis and either enforces a 30-day re-entry blackout after realized losses or knowingly accepts basis-deferral bookkeeping — decided **before Phase 1 codifies strategy logic**, not at go-live. (Cross-asset wash-sale anxiety is overstated — stocks vs. non-identical ETFs are distinct; the same-ticker case is the real one.) Professional conversation on account structure stays before Phase 4; research memos report after-cost, after-tax expected CAGR so the economics are never quoted pre-tax (QEPM, KB-07 §2; §14).

---

## 9. Stack & infrastructure recommendation

> **Note:** verified against current sources in the research pass; see §12 for citations and any flagged uncertainty.

**Language & tooling:** Python 3.12+, `uv`, `ruff`, `pydantic` models on every module boundary, `pytest` + `hypothesis` (property tests) on the money path, pre-commit, GitHub private repo, CI (GitHub Actions or local runner) executing the look-ahead audit and gauntlet smoke tests on every strategy PR.

**Data layer:**
- Norgate (US equities incl. delisted, historical index constituents, total-return adjusted) → nightly export → **Parquet files + DuckDB** as the analytical store; `exchange_calendars` for sessions; all timestamps America/New_York. Historical index-membership tables are **first-class schema**, not derived from today's ticker list; total-return series for all momentum ranking; ≥10 years of history so backtests span 2008-class regimes (KB-10).
- One caveat the digest surfaced: **the KB never mentions Norgate by name** — its data-hygiene bar is set by CRSP/Compustat, and it warns that retail feeds usually fail the point-in-time/survivorship test. Norgate's delisting-return convention and close-construction methodology therefore get *verified in Phase 0 against vendor docs and spot-checks*, not assumed. (PIT discipline is asserted independently by five KB files — the single most cross-validated requirement in the corpus.)
- Production volatility estimator standardized once, used everywhere: `σ = 0.30·σ_long-run + 0.70·σ_EWMA(span≈32d)` (KB-10).
- **Norgate access is already solved** by your existing `norgate-service` (private repo): a stateless FastAPI bridge running as an NSSM Windows service on the NDU VM, wrapping `norgatedata`, with bearer-token auth and endpoints for OHLCV, **point-in-time index membership** (`/v1/universe/{index}/membership-intervals|constituents`), watchlists and metadata, returning json/csv/**arrow/parquet** with `X-Norgate-Db-Date` headers, plus a pandas client. Phase 0 therefore reduces to: nightly sync job (bridge → Parquet/DuckDB on the Mac), the QC suite, and the *delisting/total-return verification* spot-checks. The membership-intervals endpoint is exactly what gauntlet Gate 1 (historical constituents) needs. Fallback/live-price source: broker data (Alpaca/IBKR) for execution-time sanity checks; Norgate remains the research source of truth. Kaufman's rule applies: develop and trade on the same verified data source (KB-11 §3b). One ops note: the bridge VM is now a **trading-critical dependency** — its health check joins the dead-man monitoring (stale `X-Norgate-Db-Date` ⇒ no-trade hold, same as any QC failure).
- QC suite runs on every snapshot: >4σ return outliers vs. news/index moves, OHLC sanity, missing sessions, split/dividend spot-checks (KB-11 §5).

**Backtest/execution engine:** two-tier, per §5 — updated with the verified 2026 framework landscape (§12.2):
- **Tier 1 (screening + primary research engine):** custom vectorized engine over the Parquet store (pandas/polars, optionally open-source vectorbt for speed; PRO exists at $25/mo but isn't needed). Simple, fast, fully understood — this is where de Prado/Davey's "program it yourself so you know every way the backtest can be fooled" applies, because this tier is where deception lives.
- **Tier 2 (confirmation + live), revised by the framework facts:** the framework field is thinner than it looks — backtrader is in archive mode, zipline-reloaded is dormant (last release mid-2024; usable read-only via the official `zipline-norgatedata` bundle but not a foundation), QSTrader likewise stale. **NautilusTrader is the one actively-developed backtest=live engine — but it has no Alpaca adapter** (open RFC explicitly deprioritized by the lead maintainer, Jan 2026), while its **IBKR adapter is mature including dockerized headless Gateway**. Resolution for an EOD book: **don't force a streaming engine onto a weekly-MOC workflow.** The KB itself sanctions the semi-automated pattern for low-frequency trading (Chan, KB-11 §6/§8): the *same* strategy/portfolio code that produced the backtest produces today's target portfolio; a thin deterministic order service diffs it against broker truth and submits MOC/LOC orders (Alpaca `cls`/`opg` TIF — verified supported) via `alpaca-py`, later `ib_async` (community successor to ib_insync; active, v2.0.1 Jun 2025). Parity lives where it matters — signal → target → diff — with conservative auction-fill modeling in the backtest. **NautilusTrader enters at Phase 5** if/when intraday sleeves or futures (via its mature IB adapter) justify a streaming engine.
- The KB contains a genuine build-vs-buy contradiction — de Prado/Davey say build it yourself; Narang/Chan say off-the-shelf is reasonable. Resolution (not an average): **custom where backtests lie** (data pipeline, cost model, validation harness, trials ledger, fill assumptions), **adopt maintained libraries where mechanics are commodity** (broker SDKs, calendars, indicators), with the truncate-and-compare and known-answer tests (random entry ⇒ ~50% at 1:1 R:R; "can you lose on purpose?") wrapped around everything (KB-07 §3).

**Execution model (EOD-native):** **MOC/LOC orders at the primary-exchange closing auction are the natural execution algo for a daily-rebalance book** (KB-09) — the close is the auction-determined, trustworthy EOD mark (KB-01), and it's the price your Norgate-based backtest actually uses. TWAP/VWAP/POV are institutional-scale concerns, irrelevant at $50k order sizes. Transaction-cost model, with an honesty note from review (§14): MOC fills happen in a **single-price auction**, so continuous-market spread estimators are a conservative *proxy*, not a mechanism match — the backtest charges commission + Corwin-Schultz half-spread + square-root impact `≈ ⅔·σ·√(Q/V)` (expect ~5bp one-way on liquid large caps, 2–4× on small caps, KB-09) as a deliberately pessimistic bound, and the *real* model is empirical: paper/live fills vs. the closing print, per name, feed measured slippage bands that promotion and monitoring actually use. (Roll estimator demoted to an offline diagnostic — γ₁ ≥ 0 on trending names leaves it undefined too often to be a live cross-check; §14.) Architecture rule from KB-09: keep the **four TCA models separate** — market model (lookback-only, live-safe), execution model (live), *broker model* (perfect-foresight fill simulator, **research-only, physically stripped from the live build** — a classic look-ahead leak), attribution model (post-mortem).

**Brokers:** **Alpaca first for paper + first live dollars** (clean REST API, first-class paper environment, zero commission, official MCP/SDK support), **IBKR as the destination broker** as capital and instrument needs grow (`ib_async` + headless Gateway). Honest tension to record: the KB *never mentions Alpaca* and explicitly names **Interactive Brokers as the DMA broker that avoids payment-for-order-flow** (KB-09). At EOD cadence and $2–7k order sizes, PFOF fill-quality drag is small in dollar terms — and closing-auction (MOC) orders route to the primary exchange anyway — but the decision criterion is written down: *if measured slippage vs. the cost model exceeds budget during paper/early-live, move execution to IBKR early.* Broker adapters live behind one interface so the diff-to-trades layer doesn't know which broker it's talking to.

**Execution host: dedicated VPS (decided 2026-07-07, revised after multi-LLM review — §14).** The Hilpisch rule (KB-11 §7: "never deploy from your local machine") now holds literally:
- **Sizing:** 4 vCPU / 8 GB RAM / 80 GB SSD (~$7–25/mo; Hetzner CAX/CX class or equivalent, US-East region). The execution layer is a daily compute pass over the EOD Parquet snapshot plus a weekly order wave — trivial compute; 8 GB buys headroom for a dockerized IB Gateway later (confirm arm64 image if choosing ARM, else take x86).
- **Division of labor:** VPS = execution only — nightly snapshot pull, daily compute, diff-to-trades, MOC submission, reconciliation, brakes, monitoring, heartbeat. Mac = research, backtests, gauntlet, agents, oMLX. Windows VM = Norgate bridge, unchanged.
- **Data path:** Tailscale mesh (VPS ↔ Norgate VM ↔ Mac); the VPS pulls its own nightly Parquet snapshot from `norgate-service` directly — **no Mac dependency anywhere in the trade path**.
- **Scheduling & reliability:** systemd timers with `Persistent=true`; jobs idempotent (client-order-ID order files); missed-window semantics unchanged (can't run ⇒ hold last targets + page — never catch-up-trade); external dead-man heartbeat (healthchecks.io-class) pages on missed check-ins.
- **Security:** broker keys live only on the VPS (systemd credentials / root-owned env), agent jobs on the Mac physically cannot reach them; SSH keys only, firewall default-deny with Tailscale-only ingress, unattended-upgrades on. Deployment = git pull + systemd restart, gated by the same branch protections as everything else.
- **Break-glass path:** broker mobile app remains the manual flatten path from anywhere.

**Local LLM:** oMLX serving on the M5 Max (OpenAI-compatible endpoint; model class and realistic throughput per §12). Used for the bulk-task tier only (§4.3).

**Analysis & risk libraries:** `alphalens-reloaded` / `pyfolio-reloaded` (signal IC analysis, tear sheets), `mlfinlab` or hand-rolled AFML methods (triple-barrier, purged/embargoed CV, DSR — the KB's file 15 lists mlfinlab as the reference implementation; licensing to verify), TA-Lib/`pandas-ta` (indicator features), `hmmlearn` (2-state Gaussian HMM regime overlay — the KB's worked example cut max DD 56%→24% and raised Sharpe 0.37→0.48, a Phase 5 candidate), `cvxpy` + `scipy.cluster.hierarchy` (allocation/HRP when the book has enough sleeves to matter).

**Monitoring:** DuckDB + a small Streamlit (or static-HTML nightly report) dashboard: equity & drawdown curve, efficiency ratios, live-vs-sim tracking, slippage vs. model, trials-ledger burn-rate. Alerts: Telegram/ntfy. Log financial events (signals, orders, fills, P&L), not just software events (Hilpisch/Narang, KB-11 §7).

### 9.1 Conflicts the KB itself contains — resolved, not averaged

Surfaced deliberately (they'd otherwise leak into the code as inconsistency):

1. **Build vs. buy** (de Prado/Davey "program it yourself" vs. Narang/Chan "off-the-shelf is fine") → resolved above: custom where backtests lie (Tier 1, data, costs, validation), maintained open-source where mechanics are commodity (Tier 2), parity tests wrapped around both.
2. **Per-trade risk cap** (0.5–1% vs 2% vs ≤5%, all inside KB-08) → picked 10bp ATR-risk sizing + 10% position cap (§8), Clenow-consistent for a 20–25 name book.
3. **Stops** (KB-08: help trend, hurt mean reversion; Clenow momentum runs stopless) → **no global stop rule on the platform**; stops are a per-strategy-family parameter, and the risk layer's protection is sizing + drift bands + portfolio brakes, not per-position stops.
4. **HRP vs. mean-variance** (KB-04 cites HRP winning OOS generally *and* a case where plain MV won) → benchmark allocators on our own sleeve-return data when we have ≥4 sleeves; until then, vol-targeted fixed weights with IDM (no optimizer to fight).
5. **Seasonality** (Carver rejects calendar effects; Gray & Vogel's quarter-end rebalance timing is validated) → reconcile by mechanism: structural flow-driven timing (rebalance/window-dressing) is admissible as *execution timing*; astrology-adjacent calendar signals are not admissible as *alpha*.
6. **Blend vs. sequence factors** (KB-04/14: rank-by-value-then-filter-by-quality beat blended composites in the tested construction) → the strategy interface supports both; the gauntlet decides per strategy; default to sequential filtering for value-family hypotheses.
7. **Broker silence** (KB names IBKR/DMA, never Alpaca) → §9 broker paragraph: Alpaca for paper/early live on API ergonomics, with a written slippage-based tripwire to move to IBKR.

---

## 10. Roadmap (phased, each with success criteria — loop until verified)

**Phase 0 — Data spine (now ~1 week; the hard part already exists).**
Nightly sync job consuming `norgate-service` (arrow/parquet endpoints) → Parquet + DuckDB on the Mac; universe + historical constituent tables from the membership-intervals endpoint; total-return series; QC suite; bridge-health monitoring wired into the dead-man switch.
✅ *Success:* nightly snapshot lands unattended 5 days straight; QC green; **delisting/total-return spot-checks pass against known corporate actions** (the KB-mandated Norgate audit — §9).

**Phase 1 — Validation harness before any strategy (2–3 weeks).**
Tier-1 vectorized engine + cost model (commission + half-spread + √-impact); walk-forward runner (frozen protocol per family); PSR/DSR with exact formulas + trials ledger with dedup/lineage; monkey test (matched randomization); MC trade-shuffle; truncate-and-compare CI; **golden-replay parity test** (research path vs. live dry-run path — identical targets/orders required); known-answer calibration tests; **live Alpaca-paper MOC probe** (submit `cls` orders, confirm acceptance + fill at/near the official closing print — before Phase 2 depends on it); wash-sale/lot-accounting decision coded into the strategy interface; the equal-weight benchmark defined *in code* (equal-weight universe, weekly rebalance, total-return, same cost model) so Gate 6 is computable, not vibes.
✅ *Success:* harness passes known-answer tests (random 1:1 entry ⇒ ~50%; deliberately-broken look-ahead strategy is caught by CI); golden-replay parity green; paper MOC probe verified; every run auto-logged to the ledger.

**Phase 2 — Baseline book, paper (2–3 weeks).**
Implement 2–3 baselines from the KB's fully-specified catalog — chosen for low correlation to each other, and because calibrating the harness against known published results is itself a validation step:

| Baseline | Exact spec (KB) | Role |
|---|---|---|
| **Clenow equity momentum** (primary) | Rank S&P 500 by annualized 90-day exponential-regression slope × R²; ATR20 risk-parity sizing at **10bp** of equity per position (~20–25 names); new buys only when index > 200-day SMA; weekly sell→rebalance→buy with 5% drift band; sell on rank exit from top 20%, price < 100-day MA, >15% gap, or index removal; **no stop-loss, never short** (KB-02, KB-08, KB-11 §9a) | Core sleeve |
| **ETF trend/dual momentum** | 50/100-day SMA direction filter + breakout entry + 3×ATR trailing stop over a diversified ETF basket, ATR vol-parity sizing (Clenow *Following the Trend* adapted to ETFs; KB-02) | Diversifier (works when equity momentum's regime gate is off) |
| **RSI(2) mean reversion** (candidate, Phase 3+) | RSI(2) thresholds 10/90 on liquid index ETFs, 1-day exit (KB-02/KB-03); convergent counterweight to two divergent sleeves — but MR is the most execution- and data-sensitive family (bad ticks *inflate* MR backtests, KB-07), so it enters through the full gauntlet later, not as a day-one baseline | Future convergent sleeve |

Full gauntlet on each; verify against published result ranges before trusting the harness. Tier-2 engine + Alpaca paper. Ops: alerts, dashboard, reconciliation.
✅ *Success:* 4+ weeks unattended paper trading; daily live-vs-sim reconciliation in bands; backtest metrics in the same ballpark as the published systems (a harness calibration check); kill-switch and dead-man tested by deliberately breaking things.

**Phase 3 — Agent research loop v1 (2–4 weeks).**
Pre-registration template, headless Claude Code jobs (§7), PR workflow, memo format, trial budget. Run ≥10 hypotheses end-to-end (mostly variations on the validated bases).
✅ *Success:* ≥10 hypotheses through the gauntlet with correct ledger accounting; ≥1 survivor or well-documented kills; zero constitution violations; your review time <30 min/hypothesis.

**Phase 4 — Live capital, ramped (ongoing from ~month 3–4).**
$5–10k initial allocation across the paper-graduated book; concave ramp; monthly reviews; 6-month monkey re-tests; add IBKR as second broker past ~$25k live (IB Gateway lands on the existing VPS — 8 GB sizing already accounts for it).
✅ *Success:* 3 months live with efficiency 70–100%, no unplanned manual interventions, slippage within model.

**Phase 5 — Expansion (only after Phase 4 is boring).**
More families (short-term mean reversion; value+quality annual-rebalance sleeve — EV/EBIT + F-score/GPA per KB-04/14; futures trend via Norgate futures + IBKR — Carver's *Advanced Futures* playbook incl. dynamic optimization for small accounts, KB-11 §1a-ter); HMM regime overlay (KB-08); news/sentiment ingestion for the local model; options income sleeve (needs separate data — Norgate has none; ORATS et al.); possibly fine-tuning a local model on your own accumulated memos. Two books the KB flags as worth acquiring for this phase: Cartea/Jaimungal/Penalva (*Algorithmic and High-Frequency Trading* — rigorous execution math) and Isichenko (*Quantitative Portfolio Management* — end-to-end equity stat-arb). This build order matches KB-15's own recommendation: overfitting literature first → prototype vectorized → production event-driven → point-in-time data before any real backtest → ML/LLM approaches last, held to the same OOS standard.

**What deliberately not to build** (senior-engineer scope control): intraday anything; DL price predictors as first-class alphas (KB-06's ICs say no); LLM-at-trade-time; auto-merge to live; a custom event engine from scratch if a maintained one passes the parity tests; multi-user/product features — this is a personal instrument.

---

## 11. Costs & honest economics

| Item | Est. monthly |
|---|---|
| Norgate subscription (existing) | ~$25–90 depending on package |
| Claude API/subscription for scheduled research jobs | ~$50–200 (budget-capped per job; local model absorbs bulk tasks) |
| Windows VM or VPS for Norgate updater + Linux VPS for execution | ~$10–30 |
| Misc (alerting, backups) | ~$5 |
| Backups/storage growth, heartbeat service | ~$5–20 |
| **Total** | **~$120–350/mo ≈ 3–8% of a $50k book per year** |

That drag is real: cost discipline (local models for bulk work, budget caps, batch scheduling) is part of the design, and it's another reason the near-term ROI is learning + infrastructure. The economics flip if either the book grows or the system proves worth scaling.

---

## 12. Research findings (web pass — verified against primary sources)

Method: a fan-out research workflow (96 agents; 16 primary sources fetched; 74 claims extracted; top 25 put through 3-vote adversarial verification → 21 confirmed, 4 refuted), plus direct primary-source verification of the remaining gaps. Confidence labels per finding.

### 12.1 LLM-agent trading: the replication evidence (high confidence — this section is the best-covered)

- **TradingAgents** (arXiv:2412.20138) — the flagship multi-agent "trading firm role-play" framework. Its abstract claims superiority on returns/Sharpe/drawdown but **reports no numbers in the abstract**; the architecture is real, the efficacy claim is marketing-shaped. *(3-0 verified)*
- **FINSABER replication** (arXiv:2505.07078, **peer-reviewed, KDD 2026 Oral** — strongest single source): 20-year backtest (2004–2024), 63–91 S&P 500 constituents *including delisted symbols*. **Neither FinMem nor FinAgent generates statistically significant alpha — all p-values > 0.34** (FinMem alpha −1.34%/−1.04%; FinAgent +6.57%/−0.20%, none significant). Regime behavior is exactly wrong: too conservative in bulls (Sharpe 0.12/−0.19 vs buy-and-hold 0.61), too aggressive in bears (−0.38/−0.97 vs −0.28). *(3-0, 4 merged claims)*
- **Pretraining leakage is the engine of apparent LLM-agent alpha** ("Profit Mirage", arXiv:2510.07920 + "Alpha Illusion", arXiv:2605.16895 — two independent preprints with matching numbers): across FinMem, FinAgent, QuantAgent, FinCon, TradingAgents (all GPT-4o-backed), **Sharpe decays 51–62% and total return 50–72% once the evaluation window passes the model's knowledge cutoff**; a memorization audit (FinLake-Bench) shows **85–93% recall accuracy** on historical financial facts; a counterfactual test found the worst model kept **82% of its predictions unchanged when the input data was materially altered** — the agents recite memorized outcomes rather than analyze the data in front of them. *(3-0 on the numbers; 2-1 on the broadest interpretive claims — both papers are preprints whose authors sell competing fixes)*
- **Frictions erase the rest** (Alpha Illusion): reproducing TradingAgents and QuantAgent with commissions, token costs, spread and impact drops Sharpe 0.43→0.22 and −0.96→−1.15 respectively; **both end below buy-and-hold**. *(medium confidence: single 5-ticker/1-year reproduction, wide CI)*
- **No documented real-money deployment results exist for any of the six major named systems** (FinCon, FinMem, TradingAgents, FinAgent, QuantAgent, FLAG-Trader). Every headline number in this literature is backtest-only. *(3-0)*
- Instructive refutation: FinMem's own self-reported claim ("outperformed all baselines with statistical significance") **failed adversarial verification 0-3**, while the independent large-scale replication (above) found no alpha — the textbook pattern of self-reported results dying under replication. Backbone choice also swings results wildly in FinMem's own tests (GPT-4-Turbo Sharpe 2.496 vs Llama2-70b **−2.85**). *(3-0)*
- AlphaEvolve-style evolutionary strategy search applied to trading: essentially **unresolved** — the visible open-source project (pwb-alphaevolve) is an unofficial third-party adaptation with no verified performance record either way. *(low confidence)*

**Design consequence (already baked into §1/§5):** LLMs stay in roles where the evidence supports them — code generation, research assistance, structured summarization, hypothesis drafting grounded in theory — and are structurally excluded from price prediction and trade-time decisions. The generalization caveat cuts both ways: these tests used GPT-4o-class backbones and don't directly measure the research-assistant roles this platform uses; but nothing in the verified record supports LLM-as-trader either.

### 12.2 Framework & tooling facts (verified)

| Fact | Status | Source |
|---|---|---|
| NautilusTrader IBKR adapter mature: dockerized headless IB Gateway (programmatic login via env vars), all major IB asset classes | ✅ 3-0 | nautilustrader.io docs + source inspection |
| NautilusTrader has **no official Alpaca adapter**; open RFC explicitly deprioritized by lead maintainer (Jan 2026, project at "complexity peak" mid-Rust-port) | ✅ 3-0 | github nautilus_trader issue #3374 |
| ARM64 caveat: dockerized IB Gateway historically hardcoded amd64 (issue #3813, closed) — re-verify arm64 image on the M5 Max before relying on it | ⚠️ noted | same |
| vectorbt PRO pricing: $25/mo, $240/yr, $500 lifetime; open-source vectorbt remains free | ✅ 3-0 | vectorbt.pro |
| zipline-reloaded **dormant**: latest release 3.1.1, mid-2024; no 2025–26 releases | ✅ direct check | github releases page |
| backtrader in archive mode (no releases/significant commits in years) | ⚠️ single lower-quality source, consistent with common knowledge | python.financial |
| `ib_async` is the active community successor to ib_insync (after the original author's passing, 2024): v2.0.1 Jun 2025, maintainer Matt Stancliff, BSD-2 | ✅ direct check | github ib-api-reloaded/ib_async |
| Alpaca supports **MOC/LOC/MOO/LOO natively** via `cls`/`opg` time-in-force (the execution model in §9 works on Alpaca as designed) | ✅ direct check | docs.alpaca.markets |

### 12.3 Norgate on macOS (primary-source, extracted but below the verification cut — treat as high-probability, confirm in Phase 0)

- **Norgate Data Updater (NDU) is Windows-only**: "NDU will only work under Windows" — official FAQ. The `norgatedata` Python package requires a *running NDU* on the same machine, so the Python API is effectively Windows-side too.
- **Norgate officially sanctions Mac use via virtualization** ("Parallels Desktop, VMWare, VirtualBox" — official FAQ). **Resolved in practice: your Windows VM already runs NDU + the `norgate-service` REST bridge as an NSSM service** (§9, decision 3) — the ARM-emulation question is settled by the working deployment. Remaining Phase 0 items are the staleness policy (freshness cutoff before the morning submit; hold-last-targets on stale) and the delisting/total-return audit.
- **`zipline-norgatedata`** is an official Norgate integration package (bundles for zipline-reloaded) — useful for research even with zipline dormant.
- Resulting pipeline (as in §9): Windows VM/VPS runs NDU + a small export script (`norgatedata` → Parquet incl. delisted names, historical index constituents, total-return series) → synced to the Mac → DuckDB. The export script is also where the Phase 0 *verification of Norgate's survivorship/delisting handling* happens (the KB never audits Norgate — §9).

### 12.4 oMLX (direct check)

Open-source (Apache 2.0) LLM inference server built on Apple MLX: **OpenAI-compatible (`/v1/chat/completions`) and Anthropic-compatible (`/v1/messages`) endpoints**, continuous batching (~4× generation throughput at 8× concurrency), two-tier RAM+SSD paged KV cache (agent TTFT from 30–90s down to <5s), native menubar app, any MLX-format HuggingFace model (Qwen, Llama, Mistral, Gemma, DeepSeek, GLM, MiniMax; VLMs, embeddings, rerankers). Explicitly positioned as a drop-in backend for Claude Code. Sources: omlx.ai, github.com/jundot/omlx.
**Fit:** ideal for the §4.3 bulk-task tier. On 128GB, a 70B-dense 4-bit or ~100B-class MoE 4-bit model runs comfortably with room for the KV cache; 200B+-class MoE at aggressive quantization is marginal (unverified estimate — benchmark on the machine). The Anthropic-compatible endpoint means agent jobs can be pointed at local models for cheap tasks *without changing tooling*.

### 12.5 Cross-check: the NotebookLM "Institutional Blueprint" report (reviewed 2026-07-07)

A NotebookLM-generated "Technical Blueprint: Autonomous Institutional Quantitative Trading System" was reviewed against this document. Assessment:

- **What it is:** a faithful distillation of *market-microstructure theory* — essentially Hasbrouck (Roll model, Kyle λ, Glosten-Milgrom quote updating, martingale/Wold decomposition; its own "theoretical authority" citations are Hasbrouck chapter numbers) plus a reinterpretation of ATLAS — reshaped into system-requirements language.
- **Wrong operating point for this platform:** it specifies an *intraday dealer/market-maker*: event-time point processes at second precision, LOB liquidity provision via limit orders, trade-sign conditional quote updating, Kyle-style order-splitting across auctions, Amihud-Mendelson inventory control. None of that is implementable on Norgate EOD data, and none of it is appropriate at $50k/weekly-MOC scale — the KB is explicit that latency/microstructure spend only pays when edge decays in milliseconds (KB-11 §11), and that fast limit-order strategies force exactly the automation complexity a retail EOD book should avoid (Carver).
- **Critical omission:** its "Self-Improvement Loop" section is an econometric stability condition (invertible MA representation). It contains **nothing** on multiple-testing control, deflated Sharpe, trial accounting, walk-forward gates, paper incubation, promotion/retirement lifecycle, risk constitution, or operations — i.e., the entire binding constraint of an autonomous self-improving system (§3, §5, §6 here). Aronson's 6,402-rule null result and de Prado's false-discovery math make that omission disqualifying for the stated goal.
- **Misreadings:** ATLAS is an LLM analyst-pipeline + adaptive-prompting framework, not an informed-trader detection engine; "0.0079/share price-to-quote distance" is a dated empirical constant, not a calibration protocol; "half of private information impounded per auction" is a stylized Kyle-model property, not an implementable rule.
- **Adopted from it (genuinely useful, small):** Roll-estimator spread cross-check with the γ₁≥0 fallback (now in §9's cost model); reaffirmed stationarity discipline (analyze returns/Δp, never levels — already KB policy here); uncentered (zero-mean) short-horizon vol estimation (consistent with our EWMA estimator); recency-weighting of data (already present via regime-aware validation); Hasbrouck's σ_w²/pricing-error variance retained as a *future* TCA diagnostic if intraday data ever enters (Phase 5+).
- **Net:** complementary reference for a hypothetical intraday sleeve years from now; not a competing design for this platform. The microstructure theory it summarizes is already in the KB (file 01) with the same caveats.

### 12.6 What the web pass did NOT establish (honest gaps)

- **Alpaca vs IBKR operational comparison** (API reliability stats, paper-env fidelity, measured PFOF fill-quality drag at EOD): no surviving verified claims. Mitigated by design: MOC orders route to the primary-exchange auction, and §9 has a written slippage tripwire to move to IBKR. Measure, don't assume.
- **Claude Code/Agent SDK headless automation patterns**: not externally verified — but this is your daily tooling; treat §7 as engineering design, validated by building Phase 3.
- **Anti-overfitting library landscape** (mlfinlab licensing status, timeseriescv maintenance): unverified. The formulas are fully specified in KB-07 (§4a); DSR/PSR/purged-CV are each <100 lines to hand-roll, which also fits the "custom where backtests lie" rule. Check mlfinlab's current license before importing it (it moved toward commercial licensing in the past — unverified recollection, flagged as such).
- **Retail performance distributions**: no verified external data; the KB's own numbers (live ≈ ½ backtest Sharpe, diversified ceiling ≈ 1.0, Carver's pessimism factors) remain the planning basis — they are already conservative.
- **Tax/regulatory specifics**: nothing verified; §8's note stands — one professional conversation before Phase 4.

---

## 13. Decisions (resolved 2026-07-07)

1. **Scope:** EOD US equities/ETFs core — ✅ confirmed.
2. **Autonomy ceiling:** trust ladder as drawn (human gate at merge-to-paper initially, capital gates human permanently) — ✅ confirmed.
3. **Norgate logistics:** already solved — existing Windows VM runs NDU + `norgate-service` REST bridge (github.com/vyarmak/norgate-service, private); the platform consumes its API. §9 and Phase 0 updated accordingly.
4. **Execution host:** ~~Mac~~ → **dedicated VPS** (revised 2026-07-07 after the multi-LLM review's 3-of-5 recommendation; §9 has sizing — 4 vCPU/8 GB — and the full host design). Mac remains the research machine only.
5. **Account structure / tax:** professional conversation before Phase 4 — ✅ agreed (wash-sale/lot handling itself is coded in Phase 1; §8).

---

## 14. Multi-LLM review record (2026-07-07)

Five independent reviewers (Codex, Antigravity, GitHub Copilot, OpenCode, local Qwen3.6-35B) ran adversarial passes over this document; ~60 findings, synthesized and applied. Full outputs archived in the session scratchpad.

**Consensus findings (≥3 reviewers) — all applied:**
1. **EOD-data/MOC timing contract was missing** → §4.1 timing contract (signal close T−1 → submit morning T → fill close T; freshness cutoff; manifest timestamps).
2. **"Backtest = live" was overstated for a two-tier design** → reframed to signal→target→diff parity, enforced by golden-replay CI + empirical slippage bands (§4.1, Phase 1).
3. **Trials ledger was gameable by an LLM rephrasing failed ideas** → machine-readable pre-registration, semantic dedup + lineage, family-scoped counting, orchestrator-enforced budget, stricter hurdle tier for LLM-originated families (§5).
4. **Fixed loss brakes fired on normal noise while contradicting "15–25% DD normal"** → brakes split into malfunction halts vs. vol-scaled, MC-calibrated rate-based de-risking (§8).
5. **Liquidity/concentration/correlation risk under-specified** → overlay added (ADV/spread filters, top-3 cap, beta band, correlation brake) (§8).
6. **Statistical gates under-specified for implementation** (WFE formula unbound, ONC unusable at low N, monkey randomization method, paper-gate purpose) → Gates 2–5, 8 rewritten with formulas, tiers, and numeric bands (§6).

**Notable single-reviewer catches applied:** vault anchored to LLM knowledge cutoff (Antigravity); deterministic CI gates-memo vs. agent discussion memo (Copilot); crisis-override defined as operational-only (OpenCode); sizing pipeline order + gross normalization + $1k floor (OpenCode/Copilot); Alpaca paper-MOC probe before Phase 2 (Copilot); wash-sale coding moved pre-Phase-1 (Copilot); auction-vs-spread-estimator honesty + Roll demotion (Antigravity); idle-cash T-bill sleeve (self-review); multi-model CI review demoted to advisory in favor of property tests (OpenCode + Qwen).

**Divergence — resolved in the reviewers' favor:** 3 of 5 reviewers recommended moving execution off the Mac to a VPS from day one (sleep/update/window-miss risk). Initially declined; user reversed the decision same day after reading the synthesis — execution now lives on a dedicated VPS (decision 4, §9), which also strengthens key isolation (broker credentials never on the machine agents run on).

**Rejected findings (for the record, with reasons):** "DSR > 0.95 is an inverted p-value gate" — misreads Bailey–López de Prado's DSR (it's a probability the true Sharpe exceeds 0; higher = better; formula now cited to prevent implementer confusion). "10bp sizing = $5 risk/position" — arithmetic error (10bp = 0.001, and the vol-target scalar governs absolute risk), though it exposed the pipeline-order ambiguity now fixed. "Norgate offers minute bars, assumption too restrictive" — Norgate is EOD-only. "Monkey test trivially weak" — misreads Davey's trade-matched construction, though the randomization method is now specified. "−3% day ≈ 3σ happens ~5×/yr at 10% vol" — σ math off (daily σ ≈ 0.63%), but the direction (brakes too tight) held via other reviewers and was adopted.
