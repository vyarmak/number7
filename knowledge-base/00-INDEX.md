# 00 — Trading System Knowledge Base · Master Index

A thematic, citation-backed knowledge base distilled from **68 books and research papers (~22,000+ pages)** on trading, quantitative finance, market microstructure, options/volatility, and fundamental valuation. Built to be consulted by **LLM agents and humans** when designing and building an **equities/ETF-focused systematic trading system**.

- **Organization:** thematic (by topic), not by book. Every claim carries an inline citation to its source so it stays traceable.
- **Market weighting:** equities/ETFs first; cross-asset methods (futures, FX, options, crypto) are included and flagged where instrument-specific.
- **Depth:** balanced — concepts plus actionable detail (formulas, parameters, algorithm steps), not full transcription.
- **Built in three passes:** an initial 31-source pass; a second pass adding 31 sources (most from the recommended-books list) plus two new themes (Options/Volatility/Derivatives, Fundamental Analysis & Valuation); and a third pass adding 6 more recommended books. Theme files enriched in a later pass carry an `*Updated (pass N):*` note under their header.

---

## How to use this knowledge base (read this first if you are an agent)
- **Each file is one theme**, coded `T01`–`T14`. Filenames are numbered to match (`01-…` = T01, etc.). Auxiliary files are `15` (further reading), `16` (books to obtain), `17` (glossary).
- **Start here, then jump to the theme you need** via the table below. Files are self-contained but cross-link to each other under their `## Cross-references` section.
- **Citations** look like `(Kaufman)` or `(Chan, *Machine Trading*, p.84)`. The book ↔ theme map is in the **Source Inventory** below.
- **Every theme file ends with a `## To validate empirically` (or `## Caveats`) block** — treat those as open questions, not settled facts. Trading edges decay and backtests lie; the knowledge base is deliberately skeptical.
- **Formulas** are inline (plain text/LaTeX-ish). The **Glossary (file 17)** defines ~258 terms/acronyms/metrics with `→ NN` pointers.
- **External resources** (open-access papers, open-source frameworks, datasets) are in **file 15**; **books to acquire** are in **file 16**.
- **Files enriched in pass 2** carry an `*Updated: …*` note under their header listing the newly integrated sources.

---

## The 14 themes at a glance

| File | Theme | What's in it |
|---|---|---|
| `01-market-structure-and-microstructure.md` | **T01** | Participants & adverse selection; order books & precedence; order types; spread component models (Roll, Glosten-Milgrom, Glosten-Harris, **Kyle λ**); liquidity & price impact; **empirical stylized facts & order-flow long memory** (Bouchaud); **price-formation econometrics** (Hasbrouck) |
| `02-strategies-and-signals.md` | **T02** | The strategy catalog: trend/momentum (incl. **Clenow** full system, **Gray-Vogel** momentum), mean-reversion & stat-arb/pairs, breakout, pullback setups, **Carver** scaled-forecast framework, factor signals, event/seasonality, intraday, market-making, variance-premium strategies |
| `03-technical-analysis-and-indicators.md` | **T03** | Indicators as quantified features (formulas + params); price patterns & market structure; **Aronson's** objectivity/data-mining lesson; Heikin-Ashi, Alligator/Gator, EWMAC |
| `04-quant-alpha-factors-and-portfolio-construction.md` | **T04** | Factor zoo; **Kakushadze formulaic alphas**; **Grinold-Kahn Fundamental Law (IR≈IC·√BR)**; **QEPM** factor models; **Tortoriello** tested equity factors; **Ilmanen** style premia; alpha evaluation/combination; risk models; **advanced optimization (Black-Litterman, risk parity, HRP/NCO, shrinkage)** |
| `05-machine-learning-for-trading.md` | **T05** | ML4T workflow; supervised/unsupervised models; **time-series econometrics (Tsay: ARIMA/GARCH/cointegration)**; **López de Prado denoising, clustering, feature importance**; finance-specific validation; honest caveats |
| `06-deep-learning-and-llm-agents.md` | **T06** | DL architectures (MLP/RNN/CNN/autoencoders/GANs); deep RL for trading (+ DQN blueprints); NLP/sentiment; LLM-agent systems (ATLAS, FINMEM) & patterns; evaluation caveats |
| `07-backtesting-and-validation.md` | **T07** | Research workflow; bias families; **purged/embargoed/combinatorial CV, deflated & probabilistic Sharpe (López de Prado)**; **data-mining-bias tests, White's Reality Check (Aronson)**; **walk-forward analysis & WFE (Pardo, Tomasini)**; **Monte-Carlo & incubation gates (Davey)**; metrics & checklist |
| `08-risk-management-and-position-sizing.md` | **T08** | Sizing (fixed-fractional, ATR/vol-parity, Kelly/fractional-Kelly); **volatility targeting (Carver)**; stops; risk-of-ruin & drawdown; portfolio/factor risk; **covariance denoising/shrinkage**; VaR/ES/EVT; **fat-tails & tail risk (Taleb)**; quant-specific risks |
| `09-execution-and-transaction-costs.md` | **T09** | TCA & implementation shortfall; execution algos (TWAP/VWAP/POV/IS); efficient frontier (Almgren-Chriss); **I-Star/Kissell-Glantz impact model**; **square-root law & propagator (Bouchaud)**; order placement/SOR/dark pools; HFT execution realities |
| `10-data-and-feature-engineering.md` | **T10** | Data types/sources; data-quality pitfalls (survivorship, look-ahead, point-in-time); returns/transforms; the alpha-operator DSL; **López de Prado bars / fractional differentiation / triple-barrier labeling / microstructural features**; **pandas pipeline patterns (McKinney)**; LOB features |
| `11-system-architecture-and-implementation.md` | **T11** | The five-module quant-system anatomy (Narang); **Carver modular framework**; event-driven vs vectorized; research→production; data infra; connectivity; deployment/ops; **portfolio-of-systems**, governance, **HFT building blocks (Aldridge)** |
| `12-trading-psychology-and-discipline.md` | **T12** | Probabilistic thinking (Douglas); biases & countermeasures (**Aronson's bias catalog**, **Sinclair's prospect-theory/discipline**); behavioral-edge thesis; following & **retiring** systematic rules (Davey) |
| `13-options-volatility-and-derivatives.md` | **T13** | **NEW.** Options fundamentals & put-call parity; Black-Scholes-Merton; the Greeks (+vanna/volga); implied-vol surface/skew/term structure; realized-vol estimators & forecasting; **variance risk premium** harvesting; variance swaps, dispersion, VIX; fat tails (Taleb); futures cost-of-carry & hedging (Hull, Sinclair, Bennett) |
| `14-fundamental-analysis-and-valuation.md` | **T14** | **NEW.** Value-driver logic (ROIC, growth, WACC; economic profit); DCF/enterprise-DCF mechanics; reading statements & red flags; multiples & pitfalls; **turning fundamentals into tested factors (Tortoriello)**; fundamental factor models (QEPM); the point-in-time → factor pipeline (Koller, Chincarini-Kim) |
| `15-further-reading-papers-and-resources.md` | — | Open-access papers, open-source frameworks, datasets, curated lists |
| `16-recommended-books-to-obtain.md` | — | Remaining books to acquire (most of the original list is now in the library) |
| `17-glossary.md` | — | ~258 terms/acronyms/metrics with compact definitions, formulas, and `→ NN` pointers |

---

## Source inventory (68 documents)

**Pass 1 (original 31)** — Systematic/classical: Kaufman *Trading Systems & Methods*; Narang *Inside the Black Box*; Chan *Quantitative Trading* & *Machine Trading*; Davey *Algo Trading Cheat Codes*; Halls-Moore *Successful* & *Advanced Algorithmic Trading*. Microstructure/execution: Harris *Trading and Exchanges*; Johnson *Algorithmic Trading & DMA* (OCR); Leshik & Cralle; Guo/Lai/Shek/Wong *Quantitative Trading* (Chinese). ML/Python: Jansen *ML for Algorithmic Trading*; Hilpisch *Python for Algorithmic Trading*; Kaabar *Deep Learning for Finance*; Lachowicz *Python for Quants*; Broker & Test (low value). Quant-alpha papers (Kakushadze): *101 Formulaic Alphas*, *151 Trading Strategies*, *Statistical Risk Models*, *Mean-Reversion & Optimization*, *Decoding Stock Market*. Discretionary/TA: Grimes; Bellafiore *The PlayBook*; Aziz; Bernstein; light *Algorithmic Trading Strategies*. Psychology: Douglas *Trading in the Zone*; Hougaard *Best Loser Wins*. LLM/agent papers: ATLAS, FINMEM, Autonomous Bidding Agents.

**Pass 2 (new 31)**

*Systematic development & robustness:* Carver *Systematic Trading* → T02,T08,T11; Clenow *Following the Trend* → T02,T08; Davey *Building Winning Algorithmic Trading Systems* → T07,T08; Tomasini & Jaekle *Trading Systems* → T07,T02,T08; Pardo *The Evaluation and Optimization of Trading Strategies* → T07.

*Microstructure & execution:* Hasbrouck *Empirical Market Microstructure* → T01; Bouchaud, Bonart, Donier & Gould *Trades, Quotes and Prices* → T01,T09; Kissell *The Science of Algorithmic Trading and Portfolio Management* → T09; Aldridge *High-Frequency Trading* → T01,T09,T11; Narang *The Truth About High-Frequency Trading* (short) → T01.

*ML / data / quant methods:* López de Prado *Advances in Financial Machine Learning* → T07,T10,T05,T08; López de Prado *Machine Learning for Asset Managers* → T05,T04,T08; Tsay *Analysis of Financial Time Series* → T05,T08; Jurczenko (ed.) *Machine Learning for Asset Management* → T05,T04; Tatsat, Puri & Lookabaugh *ML & Data Science Blueprints for Finance* → T05,T06; McKinney *Python for Data Analysis* → T10,T11; Robbins *Quantitative Asset Management* → T04,T05,T11; Noguer *Quantitative Portfolio Optimization* (2025) → T04,T08.

*Alpha, factors & portfolio:* Grinold & Kahn *Active Portfolio Management* → T04,T08; Chincarini & Kim *Quantitative Equity Portfolio Management* → T04,T14,T08; Tortoriello *Quantitative Strategies for Achieving Alpha* → T04,T14; Ilmanen *Expected Returns* → T04,T02; Gray & Vogel *Quantitative Momentum* → T02,T04.

*Options & volatility (→ T13):* Hull *Options, Futures, and Other Derivatives*; Sinclair *Volatility Trading*; Bennett *Trading Volatility*; Taleb *Dynamic Hedging* (also T08 tail risk).

*Fundamental valuation (→ T14):* Koller, Goedhart & Wessels *Valuation* (McKinsey).

*Light retail (low value):* Heikin Ashi Trader *Scalping is Fun*; SmartMoney *Trading With Technical Trend Indicators* → T03,T02.

**Pass 3 (new 6)**

- Chan *Algorithmic Trading: Winning Strategies and Their Rationale* → T02,T04,T07,T08 (mean-reversion vs momentum **with rationale**; stationarity/cointegration tests; the four causes of momentum)
- Natenberg *Option Volatility and Pricing* → T13 (the canonical practitioner options text: pricing, the Greeks, spreads, skew, position risk)
- Gray & Carlisle *Quantitative Value* → T14,T04,T12 (the value+quality screen: Beneish M-score, Altman/Ohlson distress, Piotroski F-score, GPA, EV/EBIT; the "model is the ceiling" discipline evidence)
- Clenow *Stocks on the Move* → T02,T08,T11 (equity-momentum system: exponential-regression-slope × R² ranking, ATR risk-parity sizing, index regime filter)
- Carver *Advanced Futures Trading Strategies* → T02,T04,T08,T11 (carry/skew/value/cross-sectional rules, forecast combination, dynamic optimization for small accounts)
- Coqueret & Guida *Machine Learning for Factor Investing* → T05,T04,T07,T10 (factor investing as supervised learning; penalized/tree/NN models; interpretability; ML-backtest perils)

**Skipped as duplicates** (in `processed/skipped-duplicates/`): (pass 2) *Trading Systems and Methods* (Kaufman) and two *Inside the Black Box* editions (Narang); (pass 3) re-added copies of *Quantitative Equity Portfolio Management* (Chincarini & Kim) and *Systematic Trading* (Carver), both already processed in pass 2. Ask if you want the 2nd-edition Narang delta processed.

---

## Cross-source executive summary (if you read nothing else)
1. **The system is five modules** (Narang): *alpha → risk → transaction-cost → portfolio-construction → execution*, over a data layer and a research layer; Carver gives a concrete modular implementation of this (→ 11).
2. **Your biggest enemy is self-deception.** The validation arsenal is now deep: walk-forward + **purged/embargoed/combinatorial CV**, **data-mining-bias correction** (White's Reality Check), and **deflated/probabilistic Sharpe** to discount for the number of trials. Aronson's 6,402-rule study found *no* surviving edge after correction — assume your backtest is optimistic (→ 07).
3. **Edges are small, statistical, and decay.** `IR ≈ IC·√breadth` (Grinold-Kahn) is the master equation of active management: tiny per-bet skill (IC≈0.03–0.05) only pays off through breadth and discipline (→ 04, 12).
4. **Risk control and sizing dominate long-run results.** Volatility-target the book (vol scalar = cash-vol-target ÷ instrument vol; half-Kelly), cap exposure, and respect fat tails — Gaussian VaR understates them (Carver, Taleb) (→ 08).
5. **Three durable equity edges recur:** cross-sectional **momentum** (12-2 + path quality), **value/quality** factors (FCF/price, EV/EBITDA, ROIC — Tortoriello), and **mean-reversion/stat-arb**. Combine low-correlation alphas and neutralize exposures (→ 02, 04, 14).
6. **Costs and execution are part of the alpha.** Market impact follows a **square-root law** (≈ σ·√(Q/V)); model it (I-Star/Kissell-Glantz), measure implementation shortfall, and respect capacity (→ 09).
7. **Backtest and live should run the same event-driven code** (→ 11, 07).
8. **Options/volatility offer an adjacent edge and a risk lens:** the **variance risk premium** (implied > realized) is harvestable but tail-risky; the Greeks/vol-surface also inform hedging and signals (→ 13).
9. **ML and DL help but don't rescue a weak signal**; hold them to the same out-of-sample standard, and prefer denoised covariances and clustered feature importance (López de Prado) (→ 05, 06).

---

## Suggested build path for the trading-system project
1. **Foundations & guardrails:** read **07 (backtesting/validation)** and **08 (risk)** first. Skim **11 (architecture)**.
2. **Pick a market & data:** secure point-in-time, survivorship-bias-free equity + fundamentals data (→ 10, 14, file 15 §7).
3. **Generate hypotheses:** **02 (strategies)** + **04 (alpha factors)** + **14 (fundamentals-as-factors)** + **03 (indicators as features)**; encode signals with the alpha-operator DSL and López de Prado bars/labels (→ 10).
4. **Build the research loop:** event-driven backtester with realistic costs (→ 09, 11), validated per **07** (walk-forward + purged CV + deflated Sharpe).
5. **Sizing & portfolio construction:** **08** + **04** (vol targeting, neutralize, optimize with shrinkage/HRP).
6. **Optionally:** ML/DL/agents (**05**, **06**) and an options/vol overlay (**13**) — only after a clean baseline exists.
7. **Operate with discipline:** **12** — let rules/automation hard-code against your biases, and pre-commit quit-rules for retiring strategies.

---

## Coverage, caveats & provenance
- **Balanced depth:** notes capture key concepts and actionable detail, not every formula. Page/chapter references point back to sources.
- **Formats:** pass-2 added EPUB sources (cited by chapter/section, since EPUBs have no fixed pages) alongside PDFs (cited by page). One pass-1 source (*Algorithmic Trading & DMA*) was OCR'd (execution chapters only).
- **Low-value sources** (*ML for Algorithm Trading* by Broker & Test; the light *Algorithmic Trading Strategies*, *Scalping is Fun*, *Trading With Technical Trend Indicators*) are flagged as such in their themes.
- **Equities weighting:** cross-asset, options, and fundamental material is included but framed for an equities/ETF systematic system.
- **LLM-agent material moves fast:** files 06 and 15 note recent (post-2024) work; treat agent-trading results as exploratory.
- **Generated:** June 2026, from the PDFs/EPUBs in this folder, across two passes. This knowledge base is a study/design aid, **not** financial advice or a guarantee of any strategy's profitability.
