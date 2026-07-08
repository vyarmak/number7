# 15 — Further Reading: Papers, Frameworks & Data Resources
*Trading System Knowledge Base · curation file · equities/ETF-weighted*

**Purpose:** Open-access papers, open-source software, and data sources that extend the books in this library. Prioritized for building an equities-focused systematic/quant system. Where a link may rot, the full citation lets you find it by name on arXiv, SSRN, or Google Scholar.

---

## 1. Research hygiene & backtest overfitting (read these before trusting any backtest)
This is the highest-leverage external reading: it protects you from the #1 way quant projects fail.

- **Bailey, Borwein, López de Prado & Zhu (2014), "Pseudo-Mathematics and Financial Charlatanism: The Effects of Backtest Overfitting on Out-of-Sample Performance"** — *Notices of the AMS*. Proves that testing even ~45 configurations on 5 years of data can produce a spuriously high Sharpe. [SSRN 2308659](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2308659)
- **Bailey & López de Prado (2014), "The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality"** — *J. Portfolio Management*. Gives the deflated/probabilistic Sharpe formulas used in theme **07**. [SSRN 2465675](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2465675)
- **López de Prado (2014), "Determining Optimal Trading Rules without Backtesting"** — avoids overfitting profit-target/stop rules. [arXiv 1408.1159](https://arxiv.org/pdf/1408.1159)
- **López de Prado (2016), "Building Diversified Portfolios that Outperform Out-of-Sample"** — *J. Portfolio Management*. Introduces **Hierarchical Risk Parity (HRP)**, a robust alternative to mean-variance (theme **04, 08**). Find on SSRN by title.
- **Harvey, Liu & Zhu (2016), "…and the Cross-Section of Expected Returns"** — *RFS*. The "factor zoo" / multiple-testing problem; why most published factors are noise. Find on SSRN.

## 2. Execution & market microstructure
- **Almgren & Chriss (2000), "Optimal Execution of Portfolio Transactions"** — *J. Risk*. The optimal-execution / efficient-trading-frontier model behind theme **09** (minimize impact + λ·variance).
- **Avellaneda & Stoikov (2008), "High-frequency trading in a limit order book"** — *Quantitative Finance*. The canonical market-making optimal-quote model (theme **01, 09**).
- **Obizhaeva & Wang (2013), "Optimal trading strategy and supply/demand dynamics"** — resilient-LOB execution (also covered in your Guo/Lai/Shek/Wong notes).
- **Gatheral (2010), "No-Dynamic-Arbitrage and Market Impact"** — the square-root impact law foundation.

## 3. Factors & asset pricing (equities)
- **Fama & French (1993), "Common Risk Factors in the Returns on Stocks and Bonds"** and **(2015), "A Five-Factor Asset Pricing Model"** — the factor backbone for theme **04**.
- **Jegadeesh & Titman (1993), "Returns to Buying Winners and Selling Losers"** — the original cross-sectional momentum result.
- **Carhart (1997), "On Persistence in Mutual Fund Performance"** — adds the momentum factor.
- **Gu, Kelly & Xiu (2020), "Empirical Asset Pricing via Machine Learning"** — *RFS*. The benchmark study showing trees/NNs beat linear models for the cross-section of returns; what works and what doesn't. arXiv/SSRN by title.

## 4. Machine learning / deep learning / RL for trading
- **Moody & Saffell (2001), "Learning to Trade via Direct Reinforcement"** — foundational RL-for-trading.
- **Deng et al. (2017), "Deep Direct Reinforcement Learning for Financial Signal Representation and Trading"** — deep RL applied end-to-end.
- **Zhang, Zohren & Roberts (2019/2020), "Deep Learning for Portfolio Optimization"** and **"DeepLOB: Deep Convolutional Neural Networks for Limit Order Books"** — strong, reproducible DL-for-markets work (theme **06**).
- **Sezer, Gudelek & Ozbayoglu (2020), "Financial Time Series Forecasting with Deep Learning: A Systematic Literature Review"** — a map of the DL-for-trading landscape.

## 5. LLM agents for trading (post-2024 — beyond your ATLAS/FINMEM PDFs)
This area moves fast; treat results as exploratory and watch for look-ahead/data-leakage with news + LLMs (see theme **06** caveats).

- **TradingAgents: Multi-Agents LLM Financial Trading Framework** (Tauric Research, Dec 2024) — a trading-firm-style team of LLM agents (fundamental/sentiment/news/technical analysts → researchers → trader → risk manager → fund manager). The most influential recent framework. [arXiv 2412.20138](https://arxiv.org/abs/2412.20138) · [GitHub](https://github.com/TauricResearch/TradingAgents)
- **FinAgent / FinMem** — reflection-driven agents with layered memory + multimodal inputs (FinMem is already in your library). Good design patterns for an agent memory layer.
- **FinGPT** (AI4Finance) — open-source financial LLM stack (data pipelines, sentiment, fine-tuning). [GitHub](https://github.com/AI4Finance-Foundation/FinGPT)
- **FinRL** (AI4Finance) — open-source deep-RL-for-trading framework with paper trail; treat as a research sandbox, not production. [GitHub](https://github.com/AI4Finance-Foundation/FinRL)
- *Caveat:* many 2025–2026 agent papers report strong backtests on short, recent windows where the base LLM may have memorized outcomes. Demand walk-forward, out-of-knowledge-cutoff testing, and realistic costs before believing any of it.

## 6. Open-source frameworks & libraries
**Backtesting / research engines**
- **Qlib** (Microsoft) — AI-oriented quant platform covering the full chain: data, alpha, risk, portfolio, execution. Best all-in-one research platform. [github.com/microsoft/qlib](https://github.com/microsoft/qlib)
- **NautilusTrader** — high-performance, event-driven, production-grade; same code backtest→live (Rust core, Python API). Strongest path to live trading. [nautilustrader.io](https://nautilustrader.io/)
- **vectorbt** — extremely fast vectorized backtesting (pandas/NumPy/Numba) for screening thousands of parameterizations. [github.com/polakowo/vectorbt](https://github.com/polakowo/vectorbt)
- **zipline-reloaded** — maintained fork of Quantemica/Zipline by Stefan Jansen (author of your Jansen book); pairs with **alphalens-reloaded** and **pyfolio-reloaded**. [github.com/stefan-jansen/zipline-reloaded](https://github.com/stefan-jansen/zipline-reloaded)
- **backtesting.py** — lightweight, clean single-asset backtester for quick prototypes. [github.com/kernc/backtesting.py](https://github.com/kernc/backtesting.py)
- **backtrader** — feature-rich, huge example archive; great for learning but watch maintenance/scaling in 2026. [github.com/mementum/backtrader](https://github.com/mementum/backtrader)
- **LEAN / QuantConnect** — broker-integrated engine (Python/C#) with hosted data; fast path to paper/live. [github.com/QuantConnect/Lean](https://github.com/QuantConnect/Lean)

**Factor / performance / indicator tooling**
- **alphalens-reloaded** — alpha-factor evaluation (IC, quantile tear-sheets) — theme **04**. [github.com/stefan-jansen/alphalens-reloaded](https://github.com/stefan-jansen/alphalens-reloaded)
- **pyfolio-reloaded / empyrical-reloaded** — performance & risk tear-sheets (Sharpe, drawdown, etc.) — theme **07, 08**.
- **TA-Lib** and **pandas-ta** — technical-indicator libraries — theme **03**. [github.com/TA-Lib/ta-lib-python](https://github.com/TA-Lib/ta-lib-python) · [github.com/twopirllc/pandas-ta](https://github.com/twopirllc/pandas-ta)
- **mlfinlab** (Hudson & Thames) — implements many *Advances in Financial Machine Learning* methods (triple-barrier, fractional differentiation, purged CV). Useful companion to that book.

## 7. Data sources (equities-first)
- **Free / low-cost:** `yfinance` (Yahoo, prototyping only), **Nasdaq Data Link** (ex-Quandl), **Tiingo**, **Alpha Vantage**, **FRED** (macro), **SEC EDGAR** (filings/fundamentals), **Alpaca** & **Polygon.io** (US equities, free tiers + live), **IEX**.
- **Research-grade (paid/academic):** **CRSP** and **Compustat** via **WRDS** (the academic standard for point-in-time US equity + fundamentals — essential for survivorship-bias-free backtests), **Refinitiv/LSEG**, **Bloomberg**.
- **Reminder (theme 10):** for any equity backtest you need **point-in-time, survivorship-bias-free** data with correct corporate-action adjustment; free retail feeds usually fail this.

## 8. Curated lists, strategy databases & communities
- **awesome-quant** — large curated list of quant libraries/resources. [github.com/wilsonfreitas/awesome-quant](https://github.com/wilsonfreitas/awesome-quant)
- **awesome-systematic-trading** — libraries, strategies, books, blogs. [github.com/paperswithbacktest/awesome-systematic-trading](https://github.com/paperswithbacktest/awesome-systematic-trading) · [github.com/wangzhe3224/awesome-systematic-trading](https://github.com/wangzhe3224/awesome-systematic-trading)
- **Quantpedia** — a searchable database of published strategies with summaries and references; good for hypothesis generation (theme **02**).
- **QuantStart** (Halls-Moore's site) — articles backing your *Successful/Advanced Algorithmic Trading* books.
- **SSRN** (Financial Economics Network) and **arXiv q-fin** — where most of the above papers live; browse `q-fin.TR` (trading) and `q-fin.PM` (portfolio management).

---

## Suggested reading order for this project
1. **Protect yourself:** the §1 overfitting papers + López de Prado *Advances in Financial Machine Learning* (book file 14).
2. **Pick a framework:** prototype in **vectorbt**/**backtesting.py**, plan production on **NautilusTrader** or **Qlib** (theme **11**).
3. **Get clean data:** secure point-in-time equity data (WRDS/CRSP if available; else Polygon/Tiingo) before any serious backtest.
4. **Generate hypotheses:** Quantpedia + the §3 factor papers + your Kakushadze alpha catalog (theme **04**), validated with alphalens.
5. **Only then** explore ML/DL/LLM-agent approaches (§4–§5), held to the same out-of-sample standard.

See `16-recommended-books-to-obtain.md` for the companion book list.
