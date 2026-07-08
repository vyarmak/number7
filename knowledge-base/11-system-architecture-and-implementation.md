# 11 — System Architecture & Implementation
*Trading System Knowledge Base · theme T11 · equities/ETF-weighted*
*Updated: includes Carver, Aldridge, Davey, Tomasini, Robbins, McKinney.*
*Updated (pass 3): added Clenow rebalance loop, Carver dynamic optimization, Coqueret & Guida pipeline.*

**What this covers:** How to actually build and run a systematic equities/ETF trading system — the canonical five-module quant anatomy, Carver's modular instrument/forecast/position framework, component responsibilities and interfaces, event-driven vs. vectorized architecture, the "portfolio of systems" architecture (combining/retiring strategies), the research-factory / research-to-production path and governance, data infrastructure, broker/data connectivity, deployment/ops (containers, cloud, logging, monitoring, fail-safes), and the genuinely-low-latency-vs-not distinction for HFT. **Why it matters:** A profitable signal is worthless if the surrounding plumbing introduces look-ahead bias, drops a connection mid-trade, or diverges from the backtest. Architecture is where edge is preserved or destroyed. **Primary sources:** Narang *Inside the Black Box* (the five-module spine); Halls-Moore *Successful Algorithmic Trading* & *Advanced Algorithmic Trading* (event-driven blueprint, QSTrader); Hilpisch *Python for Algorithmic Trading* (idea→cloud stack, deployment); Chan *Quantitative Trading* & *Machine Trading* (ATS, semi/full automation); Carver *Systematic Trading* (modular framework, operating styles); Davey *Building Winning Algorithmic Trading Systems* (portfolio of systems, going-live ops, monitoring); Clenow *Following the Trend* (continuous-contract data, day-1 go-live); de Prado *Advances in Financial Machine Learning* (research factory, strategy lifecycle, parallelization); Robbins *Quantitative Asset Management* (planning, governance, IPS, data factories); Aldridge *High-Frequency Trading* (HFT build, what's latency-specific vs transferable); Grinold & Kahn (implementation as efficient translation); Tatsat et al. *Machine Learning & Data Science Blueprints* (robo-advisor app, Python stack); Jansen (ML4T infra, Zipline); Harris (order types, automated-system non-negotiables, latency); Kaufman (system-development guidelines, platforms); McKinney *Python for Data Analysis* (pandas/HDF5 data-stack patterns); Clenow *Stocks on the Move* (the concrete daily-compute + weekly sell→rebalance→buy scheduler for an equities momentum book); Carver *Advanced Futures Trading Strategies* (dynamic optimization / greedy position-rounding to replicate a large-capital portfolio on a small account; forecast-combination vs. parallel sleeves); Coqueret & Guida *Machine Learning for Factor Investing* (the predictions→rebalanced-weights backtest engine, the ML-factor pipeline); Chan *Algorithmic Trading: Winning Strategies and Their Rationale* (backtest-engine = execution-engine, platform tiers, Kalman-filter automation of mean-reversion); plus Leshik, Wellman et al. (*Autonomous Bidding Agents*), and LLM-agent systems (ATLAS/StockSim, FINMEM).

---

## 1. The canonical quant-system anatomy (the backbone)

Narang's decomposition is the spine of this entire theme. A live quant system is **five modules over two cross-cutting foundations** (Narang, *Inside the Black Box*, p.16–19):

```
                ┌─────────────┐  ┌────────────┐  ┌───────────────────┐
   INPUTS  →    │ Alpha model │  │ Risk model │  │ Transaction-cost   │
                └──────┬──────┘  └─────┬──────┘  │      model         │
                       └───────────────┴──────────┬─┴─────────────────┘
                                                   ▼
                                    ┌──────────────────────────────┐
                                    │ Portfolio-construction model │  → target portfolio
                                    └───────────────┬──────────────┘
                                                    ▼
                                    ┌──────────────────────────────┐
                                    │       Execution model        │  → live orders
                                    └──────────────────────────────┘
        ───────────────────────────────────────────────────────────────
        UNDERNEATH ALL OF IT:   DATA layer   +   RESEARCH layer
```

**Module roles, framed as personalities** (Narang, p.67, 79, 93):
- **Alpha model** — the *optimist*: predicts in order to make money (forecast prices/returns).
- **Risk model** — the *pessimist*: controls unintended exposures (limits, not predictions).
- **Transaction-cost model** — the *frugal accountant*: *describes* cost, it does not try to minimize it; the portfolio-construction model decides whether a trade's expected alpha justifies that cost.
- **Portfolio-construction model** — the *arbitrator*: balances alpha, risk, and cost into a **target portfolio** via optimization or heuristics.
- **Execution model** — the *implementer*: turns the target into live orders.

**The diff-based control loop is the core design idea.** Portfolio construction outputs a *target portfolio*; the system diffs it against the *current portfolio*, and **the differences ARE the trades** (Narang, p.18, 112). Build around this diff, not around "trade signals."

**The structure is functions, not mandatory boxes** (Narang, p.18, 72–73). Many strategies omit the t-cost model, the portfolio-construction model, or even the execution model; risk constraints can be baked into the alpha model; recursive links are common (e.g., feeding realized execution data back into the t-cost model). Treat the diagram as discrete, swappable *functions*.

This is corroborated by independent decompositions: the Chinese-quant text frames the fund decision process as **three modules — input (rules/data) → prediction (forecast prices/returns/risk params) → portfolio construction (optimization + heuristics)** (Guo et al., p.7); and the autonomous-bidding literature describes a **perception → prediction → optimization → execution** agent loop that "generalizes to any multi-asset, multi-venue trading agent" (Wellman et al., p.34–35, 59–60). LLM-agent systems likewise adopt explicit modular splits — FINMEM's Profiling / Memory / Decision-making — precisely because modularity buys *interpretability and real-time tuning* over black-box DRL (ATLAS/FINMEM, p.1–2).

### 1a. Carver's modular framework — the retail-buildable spine

Carver gives the most *implementable* version of the same modularity for a small/retail operator, using a **car analogy**: trading rules = the **engine**; the risk/position-management wrapper = the **drivetrain** (Carver, *Systematic Trading*, ch.5). The defining design move is a **standardized interface between blocks**: a **forecast of +10 means the same thing for every rule and every instrument** (10 = an "average-strength" long; the scale runs −20…+20, capped). Because the units are normalized, *any rule can be swapped in or out without redesigning the rest*, and every step is "basic arithmetic — a calculator or spreadsheet" (no optimizer required).

**The instrument → forecast → position pipeline** (Carver, ch.5, 11):
```
Instruments
  → Forecasts          (per rule/variation; each scaled so +10 = average long)
  → Combined forecast  (forecast weights + Forecast Diversification Multiplier; cap ±20)
  → Volatility target  (translate forecast into a risk-scaled position)
  → Subsystem position (one self-contained trading system per instrument)
  → Portfolio          (× instrument weight × Instrument Diversification Multiplier)
  → Round + position inertia
  → Trades
```

- **Forecast block** — each rule emits a continuous forecast on the shared −20…+20 scale; multiple rules/variations are blended with **forecast weights** and a **Forecast Diversification Multiplier (FDM)**, then capped at ±20.
- **Position block (per instrument = "subsystem")** — the volatility target converts the combined forecast into a risk-scaled position; each instrument is a standalone subsystem so subsystems can be tested and combined independently.
- **Portfolio block** — **instrument weights** (positive, sum to 100%) set by handcrafting or bootstrapping on *subsystem-return correlations*; an **Instrument Diversification Multiplier (IDM) = 1/√(W·H·Wᵀ), capped at 2.5**, scales the book back up to target risk. **Portfolio instrument position = subsystem position × instrument weight × IDM**, then rounded to integer blocks (Carver, ch.11).
- **Position inertia (cost control)** — **do not trade unless the rounded target is >10% away from the current position**; this slashes turnover/costs with negligible pre-cost impact (only loosen/skip for very fast rules). This is the retail analogue of Narang's diff-based control loop and of QSTrader's RiskManager throttle.

**Three operating styles set the automation level** (Carver, Part Four, ch.13–15) — directly parallel to the semi- vs fully-automated split in §8:
- **Staunch systems trader** — full systematic rules, run as a daily process, fully automatable.
- **Asset-allocating investor** — a constant +10 "no-rule" forecast = a constantly-rebalanced **risk-parity** book, rebalanced weekly, *no leverage and no shorting* (so it can't always hit its vol target). The minimal-effort end of the spectrum.
- **Semi-automatic trader** — *discretionary* forecasts (the human supplies a number on the −20…+20 map, Table 16), but the position is **exited only by a systematic trailing stop**; instrument weight = 100% ÷ max bets, IDM = max bets ÷ avg bets (cap 2.5), with max bets ≤ 2.5× avg bets. This bottles discretion inside a mechanical risk wrapper.

**On automation discipline:** Carver runs live trades via manual entry or simple execution algorithms; he warns that **full automation requires full trust in the system, or you will shut it off at the first drawdown** (Carver, *Systematic Trading*, ch.1, 11) — the same operator-override failure mode Douglas flags in §8.

#### 1a-bis. Carver's *Advanced Futures* — "add a strategy = add a forecast and a weight" (the same spine, generalized)

*Advanced Futures Trading Strategies* hardens the same modular interface into a build rule: **everything is a capped ±20 forecast feeding one shared position-sizing pipeline, so adding a strategy is literally adding a forecast and a weight** (Carver, *Advanced Futures*, p.423–431). Strategy 24 generalizes the recipe to *any* quantifiable signal — **choose a sensible risk-premium rationale → compute a robust statistic → risk-normalise → smooth to optimal turnover → scale & cap → pick the strategy type** — which is the concrete authoring checklist behind the `−20…+20` forecast block above.

**Forecast-combination vs. parallel sleeves — an architectural fork** (Carver, *Advanced Futures*, p.493–495, 508–509): *daily* strategies (his Parts 1–3) net cheaply into **one combined forecast** and share the whole pipeline. But **fast strategies (S26–27) and relative-value strategies (S28–30) cannot be forecast-combined** — they run at a different data frequency, execution style, and leverage — so they run as **parallel sleeves** alongside the daily book. Two cost-aware integration patterns: **net the fast sleeve's intraday orders against the daily sleeve's pending orders** to avoid paying the spread twice, *or* **reserve a disjoint instrument set for the fast sleeve** (equivalently, set zero-position constraints for those instruments inside the dynamic optimiser). This is the futures analogue of §9's "portfolio of loosely-coupled subsystems," with an explicit rule for *when* subsystems may share the sizing pipeline and when they must be isolated.

#### 1a-ter. Carver's DYNAMIC OPTIMIZATION — replicating a large-capital portfolio on a small account

The single most notable *Advanced Futures* implementation technique is **dynamic optimization**: how to run a diversified, many-instrument book on an account too small to hold a whole-number contract in every instrument. With integer contract sizes, a small account *cannot* take the fractional positions the strategy wants, so naively rounding each position independently distorts the portfolio's risk profile. Carver reframes the problem as **tracking-error minimization**: greedily choose an *integer* set of contracts whose risk profile is **as close as possible to the ideal (large-capital) position vector**, subject to a **trading-cost penalty** and a **buffering / no-trade region** so the optimizer doesn't churn (Carver, *Advanced Futures*, ch. on dynamic optimization; sample Python on the book's website).

Implementable shape of the algorithm:
```
Inputs:  ideal position vector (what an unconstrained large account would hold),
         current integer positions, per-instrument costs, covariance/risk model.
Objective:  minimize  tracking_error(candidate, ideal)  +  cost_penalty(candidate, current)
Method:  GREEDY ROUNDING — start from zero (or current), and repeatedly add the ONE
         contract (instrument + direction) that most reduces tracking error,
         until no single addition improves the penalized objective.
Buffering:  only move toward the new integer solution if it is far enough from the
            current book (a no-trade buffer), exactly mirroring Carver's position-inertia
            rule (§1a) — don't trade for a marginal tracking-error gain.
Constraints:  zero-position constraints can carve out instruments (e.g. reserved for the
              fast sleeve, §1a-bis) or respect per-instrument limits.
```
This is the small-account counterpart to Narang's diff-based control loop: instead of "target minus current = trades," it is "the *closest integer-feasible* target minus current = trades," with cost and buffering baked into the objective. **Both dynamic optimization and the limit-order mean-reversion strategies are "almost inconceivable without a fully automated system"** (Carver, *Advanced Futures*, p.445, 498–499) — they are the part of the book that forces real automation rather than a spreadsheet. Two backtest-realism notes travel with it: **deflate backtest costs to historical currency terms** (don't price old trades at today's spreads), and **model limit fills with a ~1-hour lag** rather than assuming instant execution (Carver, *Advanced Futures*, p.459, 498–499).

---

## 2. Component responsibilities & interfaces

Whether you implement the five Narang modules or the six event-driven classes (§3), each component must expose a **clean, swappable interface** so you can A/B-test pieces without touching the rest.

- **Data handler / PriceHandler** — uniform interface over historic *or* live feeds; the rest of the system must not know which it is talking to (Halls-Moore, *Successful Algo*, p.130).
- **Strategy / alpha** — consumes bars, emits signals; *deliberately separated from the portfolio* so that many strategies can feed one portfolio (Halls-Moore, *Successful Algo*, p.140–142).
- **Risk / position sizer** — slots between signal and order; in QSTrader the **PositionSizer** then **RiskManager** sit between Strategy and ExecutionHandler, and you can "swap RiskManagers by commenting one line" to A/B-test risk overlays (Halls-Moore, *Advanced Algo*, p.359–361, 476).
- **Transaction-cost model** — *describe* costs; needs intraday trade+quote capture for midpoint-based estimators (effective/realized/implementation-shortfall) — daily-only data forces VWAP/open/close benchmarks with known biases (Harris, p.427).
- **Portfolio** — outputs target; diffs against current. In the event-driven blueprint, Portfolio is the largest component and tracks `all_positions`/`current_positions` and `all_holdings`/`current_holdings` (cash, commission, total) (Halls-Moore, *Successful Algo*, p.142–150).
- **Execution** — implements the target portfolio; build-vs-buy decision (FIX engine, exec algos) recurs here (Narang, p.76, 117–118).

**Build vs. buy recurs at every module** — risk models, t-cost models, execution algos, FIX engines, data, hardware (Narang, p.76, 117–118, 128–130). Off-the-shelf is fast and reasonable but generic; custom is justified only for latency-sensitive or high-volume players.

**Reserve a discretionary override ("panic button").** Even fully systematic shops keep the right to pull names from the tradable universe on credible news (a merger spiking a price) or cut overall leverage in unmodellable crises (post-9/11) — a "garbage in, garbage out" defense (Narang, p.15–16; see also Douglas's caveat in §8).

---

## 3. Event-driven vs. vectorized architecture

**Vectorized** backtests (pandas/NumPy over a full price matrix) are fast and ideal for early research, but they invite **look-ahead bias** and cannot reuse code in live trading. **Event-driven** is the production-grade choice.

**Why event-driven over vectorized** (Halls-Moore, *Successful Algo*, p.130):
- **Code reuse** — the *same code* runs in backtest and live.
- **No look-ahead** — data arrives as discrete events, so the strategy can never peek at the future.
- **Realism** — custom fills, MOO/MOC orders, transaction-cost models.
- *Downsides:* more complexity and slower (no vectorization).

### The six reusable components (Halls-Moore, *Successful Algo*, p.130–155)

1. **Event** — base class; subtypes **MARKET, SIGNAL, ORDER, FILL** passed via an in-memory **Event Queue** (Python `Queue`).
2. **DataHandler** (ABC) — uniform interface for historic *or* live feeds. `HistoricCSVDataHandler` loads per-symbol CSVs into a dict of pandas DataFrames and **merges indexes (union + reindex pad)** so tickers align bar-to-bar (needed for pairs). `update_bars()` is a drip-feed generator emitting one **MarketEvent** per heartbeat — this is what prevents look-ahead.
3. **Strategy** (ABC) — pure-virtual `calculate_signals(event)`; emits **SignalEvent** (strategy_id, symbol, datetime, LONG/SHORT/EXIT, strength).
4. **Portfolio** (instantiable, not abstract) — on each MarketEvent, `update_timeindex` marks-to-market using the **last bar close** (an approximation); consumes SignalEvents → `generate_naive_order` (a fixed **100 shares**, MKT, no risk overlay in the reference impl) → **OrderEvent**; consumes FillEvents → updates positions/holdings/cash/commission. *Position sizing / Kelly slots in here.*
5. **ExecutionHandler** (ABC) — `SimulatedExecutionHandler` fills instantly at market (no latency/slippage/partial fills) → **FillEvent** (commission via IB formula); subclass `IBExecutionHandler` for live.
6. **Backtest** — the engine. A **nested while-loop**: the **outer** loop is the "heartbeat" (temporal resolution — 0 for backtest since data is historical, >0 for live); the **inner** loop drains the Event Queue and routes: `MARKET → Strategy.calculate_signals + Portfolio.update_timeindex`; `SIGNAL → Portfolio.update_signal`; `ORDER → ExecutionHandler.execute_order`; `FILL → Portfolio.update_fill`. Ends when DataHandler sets `continue_backtest=False`.

**QSTrader** is the fuller open-source realization of the same pattern: a modular, loosely-coupled, event-driven OMS (MIT, Python 3) designed to mirror a small quant fund, with realistic IB fees ON by default, targeting equities/ETF/forex (Halls-Moore, *Advanced Algo*, p.351–354). Its event types extend to TickEvent, BarEvent, SignalEvent, SentimentEvent, OrderEvent, FillEvent, and its component chain is **PriceHandler → Strategy → PositionSizer → RiskManager → ExecutionHandler → PortfolioHandler → Statistics (Tearsheet)**.

**Production-grade event-loop idioms worth copying** (Halls-Moore, *Advanced Algo*, p.395, 404, 471):
- `PriceParser` multiplies prices by 1e8 to do **integer arithmetic**, avoiding cumulative float error (divide by `PRICE_MULTIPLIER` to read).
- deque / NumPy rolling windows for SMAs and lookbacks.
- `_set_correct_time_and_price` buffers per-ticker prices until *all* tickers for a timestamp arrive — **essential for multi-asset/pairs strategies** so you never act on a partial cross-section.

**Loosely-coupled modules can run on separate threads/clocks.** The bidding-agent system ran entertainment trading on its own thread, separate from flight/hotel, to respect different market clocks and update frequencies (Wellman et al., p.35–36, 167). Apply this when assets trade on different venues/sessions.

**Other backtest engines named in the sources:** **Zipline** (event-driven, powers Quantopian; gives point-in-time data via `Pipeline` + `CustomFactor.compute()` over a cross-section × lookback, avoiding look-ahead; `attach_pipeline` + `before_trading_start` + `run_algorithm`) and **backtrader** (Jansen, p.204–210, 53–58). Kakushadze & Serur ship a backtest engine plus annualization/regression/PCA utilities in their source-code appendix (151 Strategies, p.1–180, cross-ref only).

### 3a. The ML-factor backtest engine: a predictions → rebalanced-weights pipeline (Coqueret & Guida)

Coqueret & Guida give the cleanest *cross-sectional, periodic-rebalance* engine shape for turning a trained ML model into a portfolio — the complement to the event-driven, per-tick engine above. **Four blocks** (Coqueret & Guida, *Machine Learning for Factor Investing*, ch.12.6):

1. **Initialize variables** — dates, the asset cross-section, holders for weights/returns/turnover.
2. **One main weighting function wrapping ALL strategies** (including an equal-weight benchmark) — `predictions → weights`. Every competing model is just another implementation of this one interface, so they are compared apples-to-apples on the same rebalance grid.
3. **The rebalancing loop** — walk the rebalance dates; at each date refit/predict (or reuse a stable model — see below), call the weighting function, record the book.
4. **Performance / turnover indicators** — Sharpe, drawdown, and turnover.

Implementation details that matter:
- **Turnover needs both weights *and* asset returns**, because **pre-rebalance weights drift with returns** over the holding period — the realized weight just before a rebalance is *not* the weight you set at the last one, so turnover = |new target − drifted current|. This is the same "the differences ARE the trades" diff as Narang's loop (§1), measured across rebalance dates.
- **Hard-code or pass hyperparameters as args**, and lean on **functional programming** to speed the loop — full ML backtests "can take hours on CPU."
- **Tuning at every rebalance date is infeasible** at realistic dimensions — **dozens–hundreds of strategies × hundreds of dates × hundreds–thousands of assets × dozens–hundreds of features** (Coqueret & Guida, ch.10.4). The architectural escape is to rely on **hyperparameter stability** (pick robust settings once) and **validate on a sub-sample** rather than re-tuning inside the loop. (This is the compute-side rationale for de Prado's "vectorize → multiprocess → distribute" stack in §7.)

This `predictions → weights → rebalance → measure` engine is the *equities/ETF-native* deployment target for an ML alpha model: the model from research is serialized once (§4's pickle-the-model-and-scaler rule), then the loop replays it on each rebalance date exactly as in research, so the live path runs the validated algorithm.

### 3b. Automating mean-reversion: the Kalman filter as a self-updating estimator (Chan)

Chan's distinguishing implementation pattern for **automating mean-reversion** is the **Kalman filter**, which removes the arbitrary look-back/weighting choices that make naive moving-average MR brittle (Chan, *Algorithmic Trading*, ch.3). Three uses, all directly codeable into a `Strategy.calculate_signals`-style block:
1. **Dynamic hedge ratio / dynamic linear regression** — observable = one leg `y`; hidden state `β = [intercept, slope]` (Eq.3.5–3.6); state-transition = identity; observation model = the other leg `x` augmented with 1s. Iterating yields **(a)** a smoothly-updating hedge ratio, **(b)** the spread's moving "mean" (the intercept), and **(c)** the forecast-error std that *replaces Bollinger's moving std* — with **no look-back window or weighting scheme to pick**. Tuning is one scalar: set `Vω = δ/(1−δ)·I` where **δ=0 → plain OLS, δ=1 → wild**; Chan uses **δ = 1e-4**. (EWA–EWC pair: APR 26.2%, Sharpe 2.4.)
2. **Market-making mean-price estimator** — a single series, hidden = mean price `m`, trivial measurement equation (Eq.3.14); measurement-noise `Ve` is **scaled by trade size** (Eq.3.20: a large trade → low uncertainty → Kalman gain → 1), giving a **volume-*and*-time-weighted fair value** for quoting.
3. As a general **mean + std estimator for any MR series**.

**Practical implementation notes that travel to any equities/ETF build** (Chan, *Algorithmic Trading*, ch.3):
- **Always use a *moving* mean/std even for a "stationary" series** — the mean drifts (economy, management changes) and the variance keeps growing (an H<0.5 series still spreads with time), so a fixed full-sample mean/std silently mis-sizes. (Reinforces §5's "never standardize on full-sample statistics.")
- **MATLAB lacks native multithreading** (Parallel Computing Toolbox caps at 12 threads) — **use Java or Python for many-symbol live trading**, echoing de Prado's "multiprocess, not multithread" point (§7).
- **Colocation reduces latency only if you are physically near the broker — *ping to verify*** before paying for it (the slower-system corollary to §6/§11).
- **Data-feed quality is load-bearing:** a *broker* feed triggered unexplained losing pair trades that **stopped after switching to a third-party feed** — corroborating §5's "develop and trade on the same, verified data source." All of Chan's examples ship as **MATLAB** (downloadable from epchan.com/book2).

---

## 4. The research-to-production path

The governing principle across every source: **the live path must run the exact algorithm that research validated.** Two framings bracket *why*: Grinold & Kahn define implementation as the **efficient translation of research into portfolios** — "good implementation can't rescue bad research, but bad implementation can ruin good research" (Grinold & Kahn, p.377); and active management is a **disciplined process** (raw info → forecasts → optimized portfolio), not "buy stocks you like" — without superior information the machinery just returns you to the benchmark, and **mathematics cannot overcome ignorance** (no transformation rescues valueless information) (Grinold & Kahn, ch.22, p.578–579). Notably, *every* construction input (alphas, covariances, costs, risk aversion) is error-prone except the current portfolio, so much of "construction technique" is really *coping with noisy inputs* — attack that directly (alpha analysis, good risk/cost models, minimal constraints) rather than with optimizer tricks (p.377).

**Hilpisch's layered "idea → cloud" stack** is the canonical ladder (Hilpisch, Fig P-1, bottom→top): Python infrastructure → financial data → **strategy + vectorized backtest** → **event-based backtest** (introduces *incremental* data arrival) → **socket/real-time layer** → **broker-API order placement** → **automation/deployment**.

**The research-factory / assembly-line model** is de Prado's organizational answer to *why most quant projects fail* (de Prado, *AFML*, ch.1.2): the dominant failure is the **"Sisyphus" model** — N quants each told to produce a whole strategy solo, which forces false positives or overcrowded factor bets. Replace it with a **research factory / assembly line of specialized stations**: **Data Curators → Feature Analysts → Strategists → Backtesters → Deployment → Portfolio Oversight**, where each quant masters *one* station and discoveries come from the *process*, not from luck. This is the same separation Robbins prescribes as governance (§9) and that QSTrader bakes into its component chain. de Prado's **common-pitfall map** (ch.1, Table 1.2) is effectively the architecture-level checklist tying each station to a technique: chronological → **volume-clock** sampling (ch.2); fixed-horizon → **triple-barrier** labeling (ch.3); side+size learned together → **meta-labeling** (ch.3); non-IID weighting → **uniqueness + sequential bootstrap** (ch.4); CV leakage → **purging/embargo** (ch.7); walk-forward → **combinatorial purged CV** (ch.11–12); backtest overfitting → **synthetic data + deflated Sharpe** (ch.10–16). (The validation techniques themselves live in 05; here the point is that the *pipeline must have a station that enforces each one.*)

**Build your own components, and budget for library bugs.** AFML deliberately ships custom Python classes — "popular libraries mean more competitors at the same well" — and flags real upstream bugs to engineer around (e.g., scikit-learn issues in label handling and `class_weight`) (de Prado, ch.1.5). The framing: financial ML *learns* high-dimensional non-linear patterns and then *guides* white-box theory (testable on independent data), versus 18th-century-style linear regression that "does not learn" (ch.1.6).

**Offline → online is the deploy-time transformation** (Hilpisch, p.208–209, 291). *Offline* algorithms train on the full dataset; *online* algorithms consume data piece-by-piece and know only past/present (the realistic trading setting). To convert: collect incoming ticks into a DataFrame, **resample** to the bar length, compute features, predict, and **act on the second-to-last bar** — the last bar is incomplete when using `resample(label='right')`. **Persist the trained model + scaler** with `pickle` (`{'model':…, 'mu':…, 'std':…}`) so the live online algo loads the identical research-phase object (Hilpisch, p.290–291).

**The Automated Trading System (ATS)** simply: retrieves market data → runs the algorithm → submits orders; its core benefits are **faithful adherence to the backtest**, running multiple strategies, and speed (Chan, *Quantitative Trading*, p.79, 92–93). Chan re-implements in **C# for production** to confirm the backtest and cut latency, **reusing the strategy classes** (Chan, *Machine Trading*, p.6–9).

**The platform's single most important virtue: backtest engine = execution engine** (Chan, *Algorithmic Trading*, ch.1). One codebase serves both, switched simply by **feeding it historical vs. live data**. This **eliminates look-ahead bias and transcription discrepancies** in one move (there is no second implementation to drift), and it is what enables **true tick/event-driven (CEP) backtesting** of higher-frequency strategies. This is the same "same code in backtest and live" principle Halls-Moore bakes into the event-driven engine (§3) and Aldridge routes production+simulation through one core engine (§11) — Chan makes it the *first* platform-selection criterion. **Choose mean-reversion vs. momentum execution accordingly:** the same dual-data-source engine automates either, but mean-reversion strategies (especially limit-order market-making and pairs) are the ones that *force* full automation and CEP-style tick handling, whereas slower momentum/EOD strategies can stay semi-automated (§8).

**Process discipline matters more than tricks.** Davey insists on a *proven end-to-end development process* ("Strategy Factory," 8 steps) — patterns and findings are raw material, not finished strategies, and skipping a step sharply lowers success (Davey/Aziz, p.29–31). Kaufman's system-development guidelines reinforce this: start from a sound **premise** (not discoverable by computer testing), state it simply (Occam — added complexity adds risk more than return), **assume nothing/verify everything**, test the most important rules first, build a **transparent** (not black-box) solution, watch errors of omission (costs, risk), and question good results (Kaufman, p.110–113, 120). Prefer **transparent over complex/black-box** builds — complex ones can be silently wrong and are only "validated" by historic tests (Kaufman, p.1928).

**Paper-trade before going live** — universally recommended. It finds software bugs without real loss, **exposes look-ahead bias invisible in the backtest**, surfaces operational timing (Chan needed ~20 min to download/parse data + ~15 min to transmit orders pre-open), and a month-plus of it can reveal data-snooping bias (Chan, *Quantitative Trading*, p.89–90; Kaufman p.1930–35 adds: it verifies *implementation*, not the full risk profile — so still start small).

**When live diverges from backtest, diagnose in order** (Chan, *Quantitative Trading*, p.90–92): (1) ATS bugs → (2) ATS-vs-backtest trade mismatch → (3) higher-than-expected costs → (4) illiquid names → then the two dreaded causes: **data-snooping bias** (simplify; if the backtest collapses, the strategy is fake — find a new one) and **regime shift**. Kaufman's parallel checklist: rule misinterpreted (e.g., "confirm by volume" means vs. the 10-day average, not vs. yesterday), wrong parameter range, or works in some markets but not similar ones (Kaufman, p.1930–35). **Trade exactly the rules and the same data source you tested** (Kaufman, p.1935).

---

## 5. Data infrastructure

**Right data first** (Kaufman, p.1921–25): equities must be **split- and dividend-adjusted** (beware negative old prices breaking percentage calcs). Check outliers (>4% jumps), missing dates, and bars where O/C fall outside H–L. Critical caution: **don't develop on "clean" data then trade dirty live data** — develop on the *original dirty* data to desensitize the strategy to bad ticks.

**Point-in-time / survivorship-bias-free data is non-negotiable** for credible backtests. Zipline's `Pipeline` provides point-in-time data to avoid look-ahead (Jansen, p.204); CRSP/WRDS provides survivorship-bias-free history with close BBO (Chan, *Machine Trading*, p.3–5).

**Continuous/back-adjusted series for futures (and roll logic).** Any system trading futures alongside equities/ETFs needs a **back-adjusted continuous series**, not raw spliced contracts (Clenow, *Following the Trend*, ch.2). Preferred method: identify the liquid contract by **open interest**, splice so the *old close matches the new close* on the roll date (keep real overnight gaps), then back-adjust the entire history; naïve unadjusted/spliced series produce nonsense (natural-gas contango is the classic blow-up). Roll by switching to the contract with higher volume/open interest, and **control your own roll** — buy and sell the two legs simultaneously to avoid price-gap risk. Carry a **metadata record per market**: ticker, delivery code, point value (which is *not* the contract size for STIRs/bonds — e.g. Eurodollar point value = 1,000,000 ÷ 100 ÷ 4 = 2,500), currency, sector, margins, last trade day. Clenow uses daily data only (vendor e.g. CSI Data) and optionally a **local MySQL store to decouple from the vendor**.

**The pandas/HDF5 data-stack patterns and look-ahead hygiene in the pipeline.** The numeric core is **NumPy + pandas** with on-disk **HDF5 (PyTables)** or columnar **Parquet** for fast reload (McKinney, *Python for Data Analysis*; Hilpisch, p.19–29; Jansen, conclusions p.1013–1018). Concrete patterns worth standardizing:
- **A single timestamp-indexed `DataFrame`** is the canonical in-memory container; align multiple symbols by **reindexing to a union index and forward-filling** (the same union-and-pad merge the event-driven `HistoricCSVDataHandler` does in §3) so the cross-section is consistent bar-to-bar.
- **`resample`** is the one-line bar-builder from ticks (§4) and the rebalance-frequency tool for EOD equity/ETF strategies; with `label='right'` the *last* bin is incomplete, which is exactly why the online algo must **act on the second-to-last bar** (Hilpisch, p.290–291).
- **Avoid look-ahead in the transform itself, not just the loop.** Any feature that touches the future leaks: use **`.shift(1)`** before joining a signal to forward returns, compute rolling stats with **`.rolling(...).mean()`** (trailing windows only), and **never** `fillna`/standardize using full-sample statistics — persist the **train-phase scaler (`mu`/`std`) with `pickle`** and apply it online so the live transform is byte-identical to research (Hilpisch, p.290–291). This is the table-stakes version of de Prado's purging/embargo: leakage is prevented in the *data engineering*, before any model sees it.
- **HDF5/Parquet write-once, read-many** lets the research and production paths load the *same* serialized frames, removing a class of "the backtest used different data" divergence.

**Storage choices, by data shape** (Jansen, conclusions p.1013–1018):
- **HDF5 / PyTables** (key-value) and **Parquet** (columnar) for tabular numeric data;
- **NoSQL** (document/graph) per data shape;
- **CSV** for simple per-symbol bar files (the event-driven `HistoricCSVDataHandler` default);
- **SQLite** for lightweight relational needs;
- big data: Hadoop (Hive/Pig/HBase) → **Spark** (in-memory RDDs, pandas-like DataFrame API, good for iterative gradient-descent ML).

Hilpisch's core stack uses **PyTables (HDF5)** alongside NumPy/pandas/SciPy/scikit-learn (Hilpisch, p.19–29).

**Tick vs. bar — and order-book reconstruction.** Bars are resampled from ticks; the online algo resamples incoming ticks to bar length (§4). For microstructure work you reconstruct the limit order book: **time-match order-detail records with trade/deletion history to regenerate the time series at each event** (Guo et al., p.137–138, 145), or maintain a **binary-search-tree per side**, processing ITCH/working/canceled/fill/partial events chronologically to maintain the BBO (Chan, *Machine Trading*, p.178–181). **High-dimensional options data won't fit in memory** — read one underlying at a time and collapse strike/expiry dimensions into T×N index arrays (ATMidx, totTheta, totVega) (Chan, *Machine Trading*, p.145–150).

**Non-price inputs** (earnings estimates, dividends) usually aren't in the real-time feed — scrape/parse HTML into tabular form (Chan, *Quantitative Trading*, p.80).

**Data vendors named:** CSI/Quandl (daily), CRSP/WRDS (bias-free), Bloomberg, ORATS/iVolatility/OptionMetrics (options + IV surface), Sharadar (cheap fundamentals), Estimize (crowd earnings), RavenPack/MarketPsych (news sentiment), tickdata/Nanex/QuantGo/Algoseek (intraday/tick) (Chan, *Machine Trading*, p.3–5).

---

## 6. Connectivity (broker & data APIs, streaming)

**Broker integration pattern** (Hilpisch, p.239–243, 291–294): subclass the broker's streaming class, override its tick callback (`on_success(time, bid, ask)`) to embed trading logic — *collect tick → resample → feature → signal → create_order*. Track `self.position` (0/±1) and trade `units*(1±position)` to flip cleanly. Going live takes ~4 lines: instantiate, `stream_data(instrument, stop=N)`, close out. Brokers wrapped in the sources: **Oanda** (CFDs/net accounts; `get_history`, `stream_data`, `create_order` with SL/TSL/TP, `get_account_summary`; credentials = account_id + access_token) and **FXCM** (FX/CFDs; `create_market_buy/sell_order`, `close_all_for_symbol`, `get_open_positions`). For equities, the recurring API is the **Interactive Brokers API** (via `IbPy` / `IBExecutionHandler` in the event-driven stack; Halls-Moore, p.155; Chan, *Successful Algo* p.9–10) — note **MATLAB has no broker API, so it cannot transmit orders**; live order submission goes through Java/C#/C++ (Chan, *Quantitative Trading*, p.84–86).

**Real-time data layer = ZeroMQ sockets, PUB-SUB** — one publisher broadcasts ticks, many subscribers consume, "like a radio station" (Hilpisch, p.202–207). Server: `zmq.Context()` → `socket(zmq.PUB)` → `bind('tcp://0.0.0.0:5555')` → loop `send_string(msg)`. Client: `socket(zmq.SUB)` → `connect(...)` → `setsockopt_string(zmq.SUBSCRIBE, channel)` → loop `recv_string()`. Use **string messages (often JSON)** over pickled objects for cross-language interop; run server and clients in *separate* processes (it will not work inside one notebook).

**Semi-automated connectivity (low-frequency)** is often enough for daily/EOD equity strategies (Chan, *Quantitative Trading*, p.81–84): generate an order file (symbol, side, size) from Excel/MATLAB — *often the same code as the backtest, with fresh data* — then upload to the broker's **basket trader** (one-shot multi-symbol) or **spread trader** (monitors a pair intraday). DDE links can auto-feed last prices into Excel and submit via macro, but DDE is slow and symbol-capped (IB defaults to 100). This suits firing only a few order waves per day.

**Latency & routing** (Harris, p.13, 102–105, 551): order-routing moves orders client→broker→dealer/exchange and reports back; speed is alpha for short-horizon strategies. When two algos run the same strategy, **the first to submit wins → colocate near the matching engine**. Where order flow routes can depend on payment/inducements, not just price. (Latency tooling — indexed/floating limit orders, automated limit-order managers — is covered in 10-execution.)

---

## 7. Deployment & ops

**Deployment non-negotiables** (Hilpisch, p.296–297; Harris, p.549–551 for institutional scale):
- **Reliability** — ≥99.9% uptime, backups, redundancy; at institutional scale: fault-tolerant + redundant hardware/network/power, a hot disaster-recovery site, excess capacity, independent QA.
- **Performance** — CPU/RAM/SSD/fast net; sub-second where it matters.
- **Security** — strong passwords, SSL, disk encryption, user auth.

**Never deploy from your local machine.** A dropped connection or power blip leaves **orphaned positions / corrupted tick data** — "renting a cloud instance is the only viable option," and even the smallest DigitalOcean Droplet ($5/mo, billed hourly) suffices for dev (Hilpisch, p.296–297).

**Containerization** (Hilpisch, p.31–35): Docker image = class, container = instance. Pattern: a `Dockerfile` (`FROM ubuntu:latest` → `ADD install.sh` → `RUN`) calling a bash script that installs Miniconda + packages — ship the **same container local→cloud unchanged**. A GPU-enabled TF Docker image materially speeds NN training (Jansen, p.987). Use **Conda/Miniconda** for environments and `conda env export --no-builds` for reproducible cross-OS env files (Hilpisch, p.19–29).

**Compute scaling — parallelize the research pipeline correctly** (de Prado, *AFML*, ch.20). Stack **three levels of parallelism**: (1) **vectorize first** — replace explicit `for`-loops with matrix algebra / compiled iterators that drop into C/C++ under the hood; (2) **multiprocess across cores** — in Python use **multiprocessing, not multithreading**, because the GIL pins Python to one thread per core; `mpPandasObj` / `mpEngine` wrap async parallel execution and are hardware-agnostic (single server → HPC cluster); (3) **distribute across cluster nodes**. The work-partitioning idiom: **atoms** = indivisible tasks, grouped into **molecules** processed sequentially per thread, parallelized at the molecular level. For two-nested-loop workloads (e.g. SADF, multi-barrier first-touch, covariance on misaligned series) a plain linear partition is *unbalanced* — instead partition into a **multiple of the core count** and **front-load the queue with the heavy molecules** so cores that finish early pick up the light ones, keeping all CPUs busy. This matters because first-touch/uniqueness searches scale to ~10⁹ evaluations.

**Cloud setup** (Hilpisch, Ch.2, p.36–42): Droplet + bash install script + a **Jupyter Lab server**, password-hashed (`notebook.auth.passwd`) and **SSL-encrypted** (self-signed OpenSSL RSA cert) for browser-based dev without SSH.

**Logging & monitoring is a first-class subsystem.** Build a custom `logger_monitor()` that BOTH writes to a log file AND publishes the message over a **ZeroMQ PUB socket**; a tiny separate "Strategy Monitoring" SUB script run *locally* connects to the cloud instance's IP and prints the live stream — giving remote real-time observability of ticks/bars/signals/orders. **Log financial events (signals, features, fills, P&L), not just software events** (Hilpisch, p.297–308). *(Security gap to fix: the demo socket stream is unencrypted plaintext.)* Narang elevates monitoring to a first-class subsystem with four monitor types: **exposure monitors, P&L monitors** (intraday curves, realized vs. unrealized, hit rate), **execution monitors** (fill rates, slippage/impact), and **systems-performance monitors** (CPU, latency) — used to detect model risk and regime breaks early (Narang, p.193–195).

**Fail-safes / capacity / kill-switch.** Crashes generate volumes that overwhelm under-provisioned systems (the 1987 SuperDot printer backlog left traders unsure if orders had filled → panic); design explicitly for **excess capacity vs. cost** (Harris, p.562, 578, 583). Beware **double-jeopardy / cancel-confirm races** — exposing one order in two venues with slow cancel/quote pipes risks double fills, so fast routing/quote/cancel/confirmation pipelines are required to safely span venues (Harris, p.500, 528). The discretionary **panic button** (§2) — pull a name or cut leverage — is the human-level kill-switch (Narang, p.15–16).

**End-to-end deploy checklist** (Hilpisch, p.299–304): set broker leverage per Kelly → create Droplet → install Python env → upload scripts + config (`pyalgo.cfg`) → run trading script → monitor locally via socket.

**Toolchain & platforms named:** core Python stack — NumPy, SciPy, pandas, statsmodels, scikit-learn, matplotlib (Chan, *Successful Algo*, p.9–10; C++ only for HFT/UHFT). ML4T libraries add TA-Lib, Alphalens, pyfolio, pykalman/pywt, linearmodels (Jansen, p.53–58). Integrated **data + broker-API + backtest platforms**: Quantopian (research/backtest), **QuantConnect** (multi-asset, live via IB/OANDA), **QuantRocket** (Moonshot, IB), NinjaTrader, AlgoTrader, Deltix, QuantHouse, Lime Strategy Studio (Jansen p.1013–1018; Chan, *Machine Trading*, p.9, 178). Retail charting/backtest platforms that prevent accidental look-ahead by construction: TradeStation (EasyLanguage), MetaStock, NinjaTrader, Wealth-Lab, AmiBroker (Kaufman, p.1919–27). Davey's reality check: those same retail platforms (TradeStation / NinjaTrader / MultiCharts) make it *too easy to curve-fit*; pros lean on R / Python / MATLAB / custom code — **program the engine yourself so you know every way the backtest can be fooled** (Davey, ch.8).

**Chan's platform tiers, by skill/budget** (Chan, *Algorithmic Trading*, ch.1) — a buy-vs-build ladder that maps onto the build-vs-buy theme (§2):
- **No-code GUI (with CEP):** Deltix, Progress Apama (also expose proprietary languages).
- **Retail special-purpose:** MetaTrader (FX only), NinjaTrader, Trading Blox, TradeStation EasyLanguage.
- **Scripting / REPL — Chan's recommended tier for quants:** MATLAB (his default), R, Python — easy debugging, and they can **call Java/C++/C# broker APIs** to become execution engines (IB-MATLAB / quant2ib / MATFIX / IbPy). This is the tier where "backtest engine = execution engine" (above) is cheapest to achieve.
- **Open-source IDEs (backtest + broker connectivity):** Marketcetera, TradeLink, AlgoTrader, ActiveQuant.
- **Hard-core / lowest-latency:** C++/C#/Java + FIX/QuickFIX.

**A concrete end-to-end app stack** (Tatsat et al., *ML & Data Science Blueprints*, ch.5 robo-advisor): a wealth-management dashboard whose ML core is supervised regression predicting an investor's risk tolerance, served as a **Plotly Dash** two-panel UI (investor-input → asset-allocation/performance), loading the **pickled model via a `predict_riskTolerance` function** then running **mean-variance optimization (`get_asset_allocation`)** to allocate and plot $100-base performance — and the allocator is swappable for **eigen-portfolio / HRP / RL** models. Their recommended Python stack for such builds: scikit-learn (regressors/classifiers, clustering, PCA/TruncatedSVD, GridSearchCV, KFold, metrics), statsmodels (ARIMA/OLS), Keras/TensorFlow (Dense/LSTM), scipy.cluster.hierarchy, **cvxopt / cvxpy** (MVP optimization), **ffn** (portfolio returns/Sharpe), pandas/numpy, **pandas_datareader / yfinance** (Yahoo, FRED), NLTK+VADER for sentiment, and **backtrader** for backtesting; all case studies ship as Jupyter notebooks runnable on a hosted cloud platform with no local install.

---

## 8. Semi- vs. fully-automated operation; reconciliation

**Choose the automation level by trading frequency** (Chan, *Quantitative Trading*, p.81–86):
- **Semi-automated** (low-frequency): generate an order file from the backtest code with fresh data → basket/spread trader (§6). Fine when you fire a few order waves per day.
- **Fully automated** (intraday/HFT): a continuous loop submitting via broker API in Java/C#/C++ — needed when reacting to real-time data wave-after-wave.

**Order semantics must be encoded precisely** in any automated system. An order is **instrument + side + quantity + conditions**; use *standardized* order types to minimize miscommunication, because non-standard instructions force manual handling (Harris, p.68–69). Encode the canonical types and their exact triggers — Market, Limit (and marketable limit), Stop / Stop-limit (buy-stops above / sell-stops below; stays active even if price crosses back), MIT, and validity instructions Day/GTC/IOC=FOK/MOO/MOC, plus AON/MAQ quantity rules (Harris, p.73–84). *(Full order-type taxonomy lives in 10-execution; encode it once, share across modules.)*

**Reconciliation: the system diffs target vs. current, and the differences are the trades** (Narang, p.18, 112). At the order level, simulators like **StockSim** enforce cash/inventory/validity and return fills, positions, and cash, "yielding a complete audit trail" — and an **order-level action space** (full executable orders: type, side, size, price) is the key implementation choice because it links analytical quality directly to concrete execution (ATLAS, p.4–5, 9). Mirror this in production: every signal must resolve to a fully-specified order, and the post-fill state (positions/cash) must reconcile against the broker's reported state each cycle.

**The human is still in the loop, and that is the biggest operational risk.** A genuinely mechanical system embodies the discipline structurally — it takes *every* qualifying edge (no cherry-picking → preserves the full sample size), predefines risk, and removes discretionary fear/euphoria (Douglas, p.101–102, 162–163). But "the system mitigates errors only to the degree the operator commits to non-intervention" — most damage happens when a person overrides the rules during winning streaks (euphoria) or after losers (fear) (Douglas, p.55–57, 167). FINMEM's emphasis on a tunable, interpretable memory module is the modern answer to this: make the automated reasoning auditable so overrides are informed, not emotional (ATLAS/FINMEM, p.1–2).

---

## 9. The "portfolio of systems" architecture — combining & retiring strategies

A mature systematic operation is not one strategy but a **portfolio of loosely-coupled subsystems** feeding one book. The Halls-Moore blueprint already separates Strategy from Portfolio precisely so **many strategies can feed one portfolio** (§2); Carver's IDM math (§1a) and Narang's portfolio-construction arbitrator (§1) are the position-level glue. Davey and Clenow supply the *lifecycle and operational* discipline for building, combining, and retiring members.

**Diversification across systems is the closest thing to a Holy Grail** (Davey, *Building Winning Algorithmic Trading Systems*, ch.15). Build cheaply-uncorrelated systems by **varying one validated base system** along a single axis at a time — market, bar size, session, entry, or exit — rather than inventing each from scratch. **Verify diversification *after the fact***, never assume it: check **daily-return correlation**, **equity-curve linearity (R²)**, **max drawdown**, and **Monte-Carlo return/DD**. Davey's worked euro example combined a day-session and a night-session variant; the combined R² and return/DD (5.5 → 6.6) **beat either piece**, because returns add while drawdowns do not coincide. To combine multiple systems in Monte Carlo, **sum the *daily* results into one synthetic system** (this preserves each member's real, non-normal trade distribution instead of assuming normality).

**Going live — operations for a multi-system book** (Davey, ch.22): **one system per account** for clean attribution; **spread accounts across brokers** (Davey lost money in the PFG Best collapse — counterparty risk is real); **automate to trade exactly as developed but stay "semi-attended."** Know **where each order type is held** (PC vs. broker vs. exchange) so a crash doesn't silently drop a stop. Plan explicit **backups for PC / internet / power / broker**. **Handle rollover correctly** (for futures sleeves): you don't lose the premium on a roll — you pay roughly *2 spreads + 1 commission*; use quick-roll / leg-in / exchange-spread methods and **never a double-limit order**. Clenow adds the cash-management spine for a multi-currency book: set up **per-currency sub-accounts** (USD, CHF, EUR, GBP, HKD, JPY, CAD), manage cash so daily mark-to-market settlements and redemptions are covered, and **park excess (~65% of assets, since a futures strategy runs only 10–20% margin-to-equity) in top-tier government debt** for safety and yield (Clenow, *Following the Trend*, ch.9).

**Day-1 go-live: enter the whole existing book, not just new signals.** Both authors are emphatic that the live portfolio must *start in the state the simulation is already in*: **enter all currently-open simulated positions on day 1, each sized as of its original signal date** — otherwise live results diverge structurally from the simulation from the first day (Clenow, *Following the Trend*, ch.9; Davey, ch.22).

### 9a. Clenow's concrete rebalance ARCHITECTURE — a daily-compute + weekly trade scheduler (an implementable design)

*Stocks on the Move* gives the most directly-implementable **scheduler design** for an equities momentum book: a **daily compute pass** feeding a **weekly trading loop**, with **two distinct rebalance cadences** (roster-rebalance vs. position-size-rebalance) deliberately kept separate (Clenow, *Stocks on the Move*, Ch. 16, "Structuring the Simulation"). Crucially, **run the engine on daily data even though you act weekly** — dropping the engine itself to weekly periodicity throws away simulation granularity. (Clenow deliberately ships **no source code** — "understand and rebuild the logic"; he also picks a **single-currency US-only** universe to avoid FX simulation/hedging complexity, and notes mid/small-cap or international universes likely offer *more* momentum at higher volatility.)

**The daily compute pass — per stock, per day, compute and store:**
1. **Index-membership indicator** (1/0 from reference/constituent data — defines the tradable scope; S&P 500 is chosen for realism and free constituent data, *not* because momentum works better on large caps — it works *in spite of* their size, and the index doubles as the benchmark);
2. **Max gap** over the trailing **90 days**;
3. **ATR(20)** (the per-stock volatility input for risk-parity sizing);
4. **Risk-adjusted momentum** = annualized **90-day exponential-regression slope × R²** (the ranking score);
5. **S&P 500 200-day moving-average state** (the single regime gate for the whole book).

**The weekly trading loop — gated on the designated trade day, run strictly in order `sell → rebalance → buy`:**
```
ON each weekly trade day:
  1. SELL   any holding that:
              - left the index, OR
              - fell out of the top 100 (top ~20% of the 500-name ranking), OR
              - closed below its 100-day moving average, OR
              - gapped > 15% (the max-gap filter).
  2. REBALANCE (position-size cadence — only ON a rebalance day):
              - resize every KEPT position back to its risk-parity target,
              - but ONLY if it has drifted > 5% from target (a deviation/no-trade filter).
  3. BUY    from the TOP of the qualified ranking, risk-parity sized (ATR-based),
              adding names until cash is exhausted —
              but ONLY if the S&P 500 is ABOVE its 200-day MA (the regime gate).
```

**Why this is an architecture, not just a rule list:** it encodes **two independent schedulers on one clock**. The **weekly cadence** drives *roster* turnover (the sell/buy of names entering and leaving the top ranking), while the **rebalance-day cadence** (a slower, separate trigger) drives *position-size* maintenance — and the **5% drift filter** plus the **regime gate** are the throttles that keep both from churning. This separation of *roster-rebalance* from *position-size-rebalance* is the equities-momentum counterpart to Carver's position-inertia / dynamic-optimization buffering (§1a, §1a-ter) and Narang's diff-based control loop (§1): targets are recomputed daily, but trades fire only when a name crosses a roster threshold *or* a position drifts past its size band *on its scheduled day*. Implemented as a scheduler, it is two cron-like triggers (a weekly roster-and-buy/sell job and a less-frequent resize job) reading from one daily-updated feature store.

**Live monitoring is a quantitative subsystem, not eyeballing** (Davey, ch.23–24):
- A **"bird's-eye" equity + drawdown curve** as the always-on health view.
- Monthly **return-efficiency and drawdown-efficiency** = *actual ÷ expected*; healthy is roughly **70–100%**. Below that, the edge may be decaying or costs mis-modelled.
- **Daily tracking against `n·avg ± √n·stddev·X` bands** (or Monte-Carlo percentile bands, since real trade distributions are not normal).
- **Crucial discipline:** a genuinely positive-EV system can sit **below its −1σ/−2σ line for a long time on pure trade-ordering luck** — *do not tweak after a handful of losers.* Systematic divergence of live-vs-simulated P&L per instrument signals a **modelling bug**; random divergence is expected and fine (Clenow's "strategy follow-up": daily-track live vs. simulated P&L per instrument). This is the same retirement/decay signal de Prado formalizes as the strategy lifecycle below.

**Strategy lifecycle — how members enter and leave** (de Prado, *AFML*, ch.1.3.1.6, the "cursus honorum"): **embargo → paper trading → graduation → re-allocation → decommission.** Allocation is **concave**: small at first, grows with a real track record, **shrinks as the edge decays**, then the strategy is decommissioned. Release new variants **in parallel** with the incumbents (don't cut over cold), which dovetails with Davey's "vary one axis" diversification factory. Together these give a concrete retire/promote policy: monitor efficiency and live-vs-sim divergence (Davey/Clenow) → taper allocation as efficiency falls → decommission, while new varied subsystems graduate in.

---

## 10. Planning & governance — the research→production path as an institution

Above the code, Robbins frames the *organization* that surrounds the system, which is where research becomes production safely (Robbins, *Quantitative Asset Management*).

**Planning is the spine — quant management is largely project management** (ch.1). The deliverable is a **"fit-for-purpose" *product*, not raw returns**, defined by firm type, skill, **fund structure** (SMA / ETF / LP, in-kind redemption, tax/jurisdiction), and incentives (model how managers behave around crystallization dates). A distinctive tool is the **Liquidity Value Adjustment**, which prices gates/lockups (found worth up to ~7%/yr).

**The investment process as architecture** (ch.2): Strategic Asset Allocation expressed as **factor exposures + a risk budget** (Robbins calls asset-class + dollar weights "archaic") → Tactical AA (views vs. what's priced in) → Factor Investing → Selection → Construction → Ongoing management. This is the institutional mirror of Carver's instrument→forecast→position→portfolio pipeline (§1a).

**Governance — the part most engineering-led builds omit** (ch.3):
- A **Business Case** plus an **Investment Policy Statement (IPS)**: objectives, authority, asset mix/benchmark, **risk limits**, authorized derivatives, **cure periods**, and a **personal-trading integrity program**. The IPS is the written contract that an automated system must be *constrained* to obey (its risk limits become the RiskManager's hard bounds).
- **IDD/ODD with a DDQ** (investment/operational due diligence questionnaires) for any outsourced component.
- **Separation of governance and execution** — you may **outsource tasks, but not responsibility.**
- **Data factories + separation of data / feature / strategy teams** — for scalability *and* to **isolate overfitting from p-hacking** (the same station-based separation as de Prado's research factory in §4 and QSTrader's component chain).
- **Build-vs-buy favors transparent in-house systems**: COTS oversimplifies and loses idiosyncratic relationships — the institutional echo of Narang's build-vs-buy (§2) and Kaufman's "prefer transparent over black-box" (§4).

This is the **event-driven backtest-to-live governance wrapper**: the IPS fixes the limits, the data/feature/strategy separation prevents leakage, the concave-allocation lifecycle (§9) controls go-live exposure, and post-trade reconciliation (§8) proves the live book matches the modelled one.

---

## 11. HFT system building blocks — and what genuinely needs low latency vs. not

Aldridge's central architectural claim is that **HFT is mostly a technology business** (Aldridge, *High-Frequency Trading*, ch.7): of the man-hours, ≈ **40% coding, 20% testing, 15% model/backtest, 10% risk/validation, 10% compliance, 5% monitoring**, with ~**36 months** to a production system and costs **front-loaded then ≈ zero**. Tellingly, the *trading logic is often ~50 lines*, while **risk-management code can exceed 50,000 lines** — at speed, the system *is* the risk management.

**The HFT system pipeline** (ch.16): **core engine** (C++/Java, **FIX / ITCH / OUCH** messaging) → **quote archival** (flat files / binary BLOBs — *archive your own feed*, not just purchased data, so post-trade analysis sees exactly what the engine saw) → **post-trade analytics** (reconcile production vs. simulation) → **simulation** → **human supervision**. Development **lifecycle**: plan → analyze → design → implement → maintain.

**Build pitfalls that apply at any speed** (ch.16):
- **Message-acknowledgment loops** — keep **separate "orders sent" vs. "executions/position" counters**, or the algo double-counts and *runs away* (this is exactly Davey's "know where each order is held" and the §8 reconcile-every-cycle rule).
- **Time/quote distortion** — queue overflow and **client-side timestamps differ from server timestamps**; mitigate by **timestamping on arrival**, growing queues, and limiting the number of instruments.
- **Testing taxonomy** to bake in: **data-set** (autocorrelation consistency), **unit**, **integration**, **system** (GUI, stress, security, scalability, **reliability ≥ 99.99%**, recovery), and **use-case** tests run by **independent testers**.

**Why "backtest = live, event-driven" is non-negotiable** is sharpest here: Aldridge's pipeline literally routes production *and* simulation through the **same core engine** and then reconciles them post-trade. That is the institutional version of Halls-Moore's "same code in backtest and live" (§3) — at HFT scale, any divergence between the simulated and live event stream is a latent loss, so the engine, the archived feed, and the reconciliation step are *one* design.

**What is genuinely latency-specific — and therefore NOT needed for a slower equity/ETF system** (ch.2, 12): **FPGA/GPU hardware**, **UDP-vs-TCP** tuning, **co-location** (~**$2,350/mo**; saves ~**17–22 ms** NY↔Chicago), and **latency arbitrage** strategies. A non-latency-sensitive system can **ignore all of these**. **What transfers fully** to a daily/EOD equities or ETF operation is the *rest* of the stack — the **data archival, event-driven backtest, risk-management code, post-trade reconciliation, and execution-cost machinery**. The practical rule: spend the co-location/FPGA budget *only* if your edge decays within milliseconds (Harris's "first to submit wins → colocate," §6); otherwise put that money into data quality, redundancy, and reconciliation, which pay off at every horizon.

---

## Cross-references
- **05 — Backtesting & validation:** look-ahead/data-snooping detection, walk-forward, **combinatorial purged CV / purging-embargo** and **deflated Sharpe** (the stations de Prado's pipeline map enforces, §4), simulation-accuracy/slippage realism, parameter-sweep harnesses (`itertools.product`), performance helpers (`create_sharpe_ratio`, `create_drawdowns`); Coqueret & Guida's four-block ML-factor backtest engine and its drift-aware turnover (§3a); Carver's deflate-costs-to-historical-currency and 1-hour-limit-fill realism (§1a-ter); Clenow's "run the engine on daily data even when acting weekly" (§9a).
- **06 — Risk & position sizing:** the risk model and PositionSizer/RiskManager interfaces; Kelly leverage set at deploy time; Carver's vol-target → subsystem-position → IDM sizing chain (§1a); **dynamic optimization / greedy integer rounding** for small accounts (tracking-error + cost penalty + buffering, §1a-ter); Clenow's ATR-based risk-parity sizing and 5% drift band (§9a); IPS risk limits as the RiskManager's hard bounds (§10).
- **07 — Alpha / signal models:** what the alpha module and `Strategy.calculate_signals` produce; Carver's normalized −20…+20 forecast interface and "add a strategy = add a forecast + weight" authoring recipe (§1a, §1a-bis); Chan's Kalman-filter dynamic hedge-ratio / mean-price estimator as a self-updating MR signal (§3b); Clenow's risk-adjusted-momentum (90-day exp-regression slope × R²) ranking score (§9a).
- **09 — Portfolio construction:** the arbitrator module; target-portfolio optimization; Carver's instrument-weights + IDM portfolio block (§1a) and dynamic-optimization as integer-feasible construction (§1a-ter); the predictions→weights mapping (§3a); the **portfolio-of-systems** combination math (§9) and forecast-combination-vs-parallel-sleeves fork (§1a-bis); Clenow's roster-vs-position-size rebalance cadences (§9a); HRP/graph-based allocation as the construction layer feeding this architecture.
- **10 — Execution & transaction costs:** order types/semantics, latency tooling (FPGA/co-location — the genuinely-latency-specific list, §11), simulation realism/slippage, TCA infrastructure, broker basket/spread traders; netting fast-sleeve intraday orders against the daily sleeve's pending orders (§1a-bis); Chan's "backtest engine = execution engine" platform criterion and tiers (§4, §7); futures roll mechanics (§9).

## To validate / engineering risks
- **Backtest↔live code parity is assumed, not enforced.** Re-implementing research (Python) in C#/C++ for production (Chan) reintroduces divergence risk; without an automated cross-check the two can silently drift — build a reconciliation test that replays the same data through both.
- **Mark-to-market on last-bar-close is an approximation** baked into the reference Portfolio (Halls-Moore); for wide-spread or illiquid ETFs this overstates equity and mis-sizes positions. Validate against mid/quote where intraday data exists.
- **Plaintext monitoring sockets and self-signed certs** (Hilpisch's demo) are explicit production security gaps — encrypt the ZeroMQ stream and use real certificates before going live with capital.
- **Multi-venue cancel/confirm races** can cause double fills (Harris). Any strategy spanning venues needs verified fast cancel + confirmation pipelines and idempotent order handling, or it will eventually double-up in a fast market.
- **Most source hardware/vendor specs are dated** (Leshik's Excel-per-stock rig and 2003-era latency numbers from Harris); treat the *principles* (redundancy, colocation, excess capacity) as durable but re-benchmark concrete numbers.
- **The operator-override failure mode** (Douglas; Carver) is the largest un-engineered risk: a fully automated system still depends on a human not intervening — decide in advance what the kill-switch criteria are and who may invoke them, so panic-button use stays disciplined. Carver's corollary: don't fully automate until you trust the system enough not to shut it off at the first drawdown.
- **Day-1 go-live state mismatch** (Clenow, Davey): launching a multi-system book with only *new* signals — instead of entering the entire currently-open simulated portfolio sized as of each original signal date — makes live results structurally diverge from the simulation from day one. Snapshot and enter the full book.
- **"Below the −2σ band" overreaction** (Davey): a positive-EV system can sit under its lower Monte-Carlo/σ band for a long time on pure trade-ordering luck. Distinguish *random* live-vs-sim divergence (expected) from *systematic per-instrument* divergence (a modelling bug) before touching the system — and pre-commit to the efficiency/decay thresholds that trigger retirement (de Prado lifecycle).
- **Counterparty / single-broker concentration** (Davey, PFG Best): one system per account and accounts spread across brokers; know where each order type is physically held (PC vs. broker vs. exchange) so a crash doesn't silently drop a stop. Plan PC/internet/power/broker backups.
- **Continuous-contract construction error** (Clenow): naïve unadjusted or mis-spliced futures series produce nonsense backtests (contango blow-ups). Back-adjust off open-interest with old-close-to-new-close splicing, and carry correct per-market point values (≠ contract size for STIRs/bonds).
- **Look-ahead leaking through the data transform, not the loop** (McKinney/Hilpisch): full-sample `fillna`/standardization and untimed rolling windows leak the future even in an event-driven engine. Persist the train-phase scaler, shift before joining to forward returns, and act on the second-to-last (complete) resampled bar.
- **Governance gap on an engineering-led build** (Robbins): without an IPS (risk limits, authorized instruments, cure periods, personal-trading program) and data/feature/strategy team separation, the system has no written constraints to obey and no structural defense against p-hacking — bolt these on before scaling capital.
- **Spending latency budget you don't need** (Aldridge): co-location/FPGA/UDP tuning only pays off if edge decays within milliseconds. For daily/EOD equities/ETFs, redirect that budget to data quality, redundancy, and production-vs-simulation reconciliation, which pay off at every horizon.
- **Message-acknowledgment runaway** (Aldridge): conflating "orders sent" with "executions/position" lets an automated loop double-count and run away. Keep separate counters and reconcile sent-vs-filled every cycle, regardless of trading speed.
- **Naive independent rounding distorts a small-account book** (Carver, *Advanced Futures*): rounding each instrument's fractional target to integer contracts in isolation skews the portfolio's risk profile. Use **dynamic optimization** — greedy integer selection minimizing tracking error to the ideal vector, with a cost penalty and a no-trade buffer (§1a-ter) — and remember it is "almost inconceivable without full automation," so don't attempt it semi-manually.
- **Engine periodicity collapsed to the trade cadence** (Clenow, *Stocks on the Move*): running the *compute* engine weekly because you *trade* weekly throws away simulation granularity (gaps, MA crossings, and ranking changes that happen mid-week are missed). Keep the daily compute pass; gate trading on the weekly day (§9a).
- **Conflating roster-rebalance with position-size-rebalance** (Clenow): folding "which names are in the book" and "resize drifted positions" into one trigger over-trades. Keep them as **two separate cadences** with their own throttles (top-ranking thresholds + the regime gate for roster; a drift band — Clenow's 5% — for sizing), §9a.
- **Drifted weights mis-measure turnover** (Coqueret & Guida): computing turnover from *set* weights ignores that pre-rebalance weights drift with returns; turnover must diff the new target against the *return-drifted* current weights, which requires feeding asset returns into the turnover function (§3a).
- **Per-rebalance hyperparameter tuning is infeasible at scale** (Coqueret & Guida): at dozens–hundreds of strategies × hundreds of dates × thousands of assets × hundreds of features, re-tuning inside the rebalance loop does not finish. Rely on **hyperparameter stability** chosen once and validated on a sub-sample, not in-loop tuning (§3a).
- **Forcing incompatible strategies into one combined forecast** (Carver, *Advanced Futures*): fast and relative-value strategies differ in data frequency, execution, and leverage and **cannot** be forecast-combined with a daily book. Run them as **parallel sleeves** (netting intraday orders against pending daily orders, or carving out a disjoint instrument set), not as one more ±20 forecast (§1a-bis).
- **Two-implementation drift is avoidable by construction** (Chan, *Algorithmic Trading*): the surest defense against backtest↔live divergence is **one engine fed historical-vs-live data**, not a second production rewrite. Where a rewrite is unavoidable (Chan's own C#), the reconciliation test from the first risk item is mandatory.
- **Broker data feeds can silently corrupt signals** (Chan, *Algorithmic Trading*): a broker feed produced unexplained losing pair trades that vanished after switching to a third-party feed. Validate the live feed independently and develop/trade on the same verified source (reinforces §5).
