# 17 — Glossary
*Trading System Knowledge Base · reference · "→ NN" points to the theme file with the fullest treatment.*

## A

**ABCD pattern** — A discretionary long setup: impulsive rally to a new high-of-day (B), pullback to a higher-low support (C); enter when C holds, stop just below C, scale out at the D target. → 02

**Accruals** — An earnings-quality proxy (the non-cash portion of earnings); high accruals signal lower quality. A component of the quality factor. → 04

**ADF test (Augmented Dickey-Fuller)** — Stationarity/mean-reversion test: regress Δyₜ on yₜ₋₁ and test γ=0 (null = unit root / non-stationary; want p<0.05). Used on price levels for mean reversion and on residuals for cointegration (CADF). → 07

**ADX (Average Directional Index)** — Measures trend *strength* (not direction); >18 and rising ⇒ ~95% likely trending in expert-system rules. Derived from Wilder's DMI. → 03

**Adverse selection** — The risk that whoever fills your passive order knows something you don't; the informed-trader-driven component of the spread. Passive limit fills cluster exactly when the market trades through you (toxic flow). → 01, 09

**Alpha** — Any reasonable expected return one wishes to trade on; a transformation of raw data producing one value per asset per date that predicts cross-sectional forward returns. A *ranking* signal (long high-ranked, short low-ranked). → 04

**Alpha combo** — The production object: a weighted blend of many weakly-correlated alphas (equal-, IC-, or regression/ML-weighted), since a single alpha is rarely tradeable. → 04

**Alpha decay** — The erosion of a factor's edge as it becomes known/crowded: factor excess returns drop ~25% from discovery to publication and >50% after. Academic (public, decaying) vs proprietary alpha. → 04, 02

**Alpha model** — The "optimist" module of a quant system: predicts prices/returns to make money. → 11

**Almgren-Chriss** — Optimal-execution framework that minimizes E[cost] + λ·Var[cost], trading expected (impact) cost against timing risk; sweeping risk-aversion λ traces the efficient trading frontier. → 09

**Altman Z-score** — Bankruptcy-prediction discriminant from five ratios (working capital, retained earnings, EBIT, equity, sales — all over assets): Z = 1.2·X₁ + 1.4·X₂ + 3.3·X₃ + 0.6·X₄ + 1.0·X₅; Z<1.81 = distress zone, >2.99 = safe. A financial-strength screen in the Quantitative Value stack. → 14

**Annualization** — Scaling to yearly terms: annualized return = avg daily return × 252; annualized vol = daily σ × √252; Sharpe × √N_T (N_T = periods/yr). → 07, 08

**Amihud's λ (illiquidity)** — A cheap daily-data illiquidity proxy: |return| ÷ dollar-volume per bar; high λ = illiquid (and carries a risk premium). A coarse cousin of Kyle's λ. → 01

**AON (all-or-none)** — Order filled in full or not at all (no partials); may rest in the book. → 01

**APT (Arbitrage Pricing Theory)** — Multi-factor model R = Xb + u: X = factor exposures (loadings), b = factor returns, u = idiosyncratic returns; factor/specific returns inferred by cross-sectional regression each period. → 04

**ARIMA** — Autoregressive integrated moving-average model for a stationary-differenced return series; ARIMA(p,1,q) on log price ≡ ARMA(p,q) on log returns. → 02, 05

**ASI (Accumulated Swing Index)** — Wilder's Swing Index summed over time; trade its High/Low Swing Points with SAR stops. → 02

**ATR (Average True Range)** — MA of True Range (TR = max(H−L, |H−Cₚᵣₑᵥ|, |Cₚᵣₑᵥ−L|)); the standard volatility unit for stops and sizing; typical lookback 14 or 20. → 03, 08

**Autoencoder** — Self-supervised net that reconstructs its input; the bottleneck code is a nonlinear generalization of PCA. Variants: undercomplete, sparse, denoising (anomaly detection), VAE. → 06

**Avellaneda-Stoikov** — Optimal market-making model: a reservation price that skews away from mid as inventory grows, plus a bid/ask half-spread balancing captured spread against inventory and order-arrival risk. → 09

**Averaging down** — Adding to a losing position; generally underperforms entering full at the signal (except sustained bear markets) and is banned by most rule-sets. → 08

## B

**Backtest** — An *idealised upper bound* on live performance; valid only as validation of a pre-stated hypothesis, never as a discovery tool. → 07

**Backtest overfitting** — Fitting noise rather than signal; THE central challenge in low-SNR finance, worse than web-scale ML. Detectors: kurtosis >6–8, spiky parameter surfaces, high in-sample/negative OOS. → 07, 06

**Bar (time/tick/volume/dollar)** — Aggregation of raw ticks: time bars (fixed period), volume bars (by traded volume), dollar bars (by price×volume, robust to splits/price level). Bar size matters more than traders think. → 10

**Beneish M-score** — Earnings-manipulation detector from eight forensic-accounting indices (e.g. DSRI days-sales-in-receivables, GMI gross-margin, AQI asset-quality, accruals); M > −1.78 flags a likely manipulator. A short-side red-flag screen in Quantitative Value. → 14

**Beta neutralization** — Constructing the portfolio so β = 0 versus the market, removing the systematic leg. → 04

**Bid-ask bounce** — The transitory price oscillation between bid and ask caused by trades alternating sides; manufactures phantom (untradeable) mean reversion, so model mid-prices not trade prices. → 01, 03

**Bid-ask spread** — Inside spread = highest bid − lowest ask; itself a transaction cost. Three components: (1) order-processing, (2) inventory, (3) adverse-selection. → 01

**Black-Litterman** — Portfolio model blending equilibrium (reverse-optimized) returns Π = δΣw̃_eq with investor views P ~ N(q,Ω). → 04

**Black-Scholes-Merton (BSM)** — The closed-form European-option price: C = S₀·N(d₁) − K·e^(−rT)·N(d₂), d₁ = [ln(S₀/K)+(r+σ²/2)T]/(σ√T), d₂ = d₁−σ√T. Rests on risk-neutral *replication*; its constant-σ/no-jump assumptions break in reality, turning the single σ into a strike-/maturity-dependent surface. → 13

**Block trade** — A large trade (rule of thumb >¼ of ADV; NYSE cutoff ~10,000 sh). ~80% of blocks are seller-initiated. → 01

**Bollinger Bands** — 20-day MA ± 2σ of price (~87% coverage as prices aren't normal). A **squeeze** (bands compress to ~50% of average) flags an impending breakout; Bollinger's own use is mean-reverting. → 03

**Box spread** — A bull call spread plus a bear put spread at the same two strikes; the combined payoff is a fixed (strike-difference) cash flow at expiry, so a box is a synthetic zero-coupon bond. Trades on the financing rate and is the cleanest arbitrage check on a chain's pricing. → 13

**Breakeven implied volatility** — The implied vol at which an option position's edge nets to zero; for a vega-dominated trade ≈ entry IV ± (edge ÷ vega), i.e. the IV move that erodes the expected profit. Natenberg's quick gauge of a trade's vol cushion. → 13

**Breakout** — Entry when price clears a defined boundary (e.g. N-day high). Best entries empirically, but *most breakouts fail*; the break zone is high-volatility/low-liquidity, so slippage is worst here. → 02

**Bull flag** — Momentum continuation: a pole of large up-candles then a sideways flag; enter on a break above the consolidation high. Only take the 1st/2nd flag. → 02

**Burn-in** — In MCMC, the initial samples discarded before the chain reaches its stationary distribution. → 05

**Butterfly spread** — A three-strike, vega-neutral-ish structure (long 1 low + long 1 high, short 2 middle, equal wings); long butterfly = cheap, capped bet that spot pins the body, and a pure play on the *curvature* of the volatility smile rather than its level. → 13

## C

**CADF (Cointegrated Augmented Dickey-Fuller)** — Pairs test: OLS for the hedge ratio β, then ADF the residuals to confirm cointegration (more negative than the critical value). → 07

**Calendar (time) spread** — Long and short the same strike in two expiries (long the far month, short the near); profits from the near option's faster theta decay and is long *forward* vega — a bet on the volatility term structure rather than spot direction. → 13

**Calmar ratio** — CAGR ÷ |max drawdown| (typically over the last 3 yrs); prefer ≥1; captures fat-tail risk Sharpe misses. → 07, 08

**CAGR** — Compound annual growth rate: (E_n/E_0)^(252/n) − 1; the compounded (not average) return figure. → 07

**Capacity** — The dollar size a strategy can deploy before market impact erodes its edge; a liquidity constraint, not just an ADV figure. → 01, 09

**CAPM** — Single-factor model (excess return loads on market β only); failed empirically, motivating multi-factor (Fama-French/APT) models. → 04, 08

**Cardinality constraint** — Σ1{wᵢ≠0} = K (e.g. index tracking with K names); makes the optimization non-convex (CCQP), solved by truncation/smoothing heuristics. → 04

**Carry** — Earning the yield differential, e.g. FX carry (buy higher-yield cross) or vol carry (harvesting IV>HV ~1.35); key risk is roll/contango loss and funding-currency concentration. → 02

**CatBoost** — Gradient-boosting tree family member with native categorical handling and fast training (cf. XGBoost, LightGBM). → 05, 10

**CCI (Commodity Channel Index)** — Bounded momentum oscillator; like RSI/Stochastic/%R, gives false signals in strong trends. → 03

**Clustered feature importance** — De Prado's fix for substitution effects: single-feature MDA/MDI dilute importance across correlated substitutes, so cluster features (correlation-distance + ONC) and score the *clusters* to find the driving themes. → 05

**Cointegration** — A stationary linear combination of non-stationary price series; the basis of pairs/stat-arb: trade the stationary spread when it dislocates. Test via CADF. → 02, 07

**Continuing (terminal) value** — The post-forecast slice of a DCF, valued with the key-driver formula on a normalized first post-forecast year: CV = NOPAT_(T+1)·(1 − g/ROIC)/(WACC − g); perpetuity g must be ≤ long-run nominal GDP and ROIC should fade toward WACC absent a moat. → 14

**Conversion / reversal** — The put-call-parity arbitrage: a *conversion* = long stock + long put + short call (same strike) locks a riskless rate; a *reversal* is the mirror (short stock + short put + long call). The trade that keeps C + K·e^(−rT) = P + S₀ enforced and exposes box/parity mispricings. → 13

**Cost of carry** — The net cost of holding the underlying, embedded in the forward/future: F₀ = S₀·e^((r−q)T) for an investment asset (yield q), F₀ = S₀·e^((r+u−y)T) for a commodity (storage u, convenience yield y). The future is spot compounded at carry, not a forecast. → 13

**Combinatorial purged cross-validation** — López de Prado's CV generating many train/test group combinations (and thus far more historical paths than walk-forward), with purging and embargoing. → 07

**Commitment of Traders (COT)** — Weekly CFTC positioning report (~1 week stale); Net COT = net funds − net hedgers is stationary and highly correlated to the underlying; large hedgers are the best forecasters. → 02, 10

**Conditional Autoencoder (Gu-Kelly-Xiu)** — Models returns as loadings × premia: a feedforward branch maps characteristics → factor loadings, an autoencoder branch maps returns → factor premia; a nonlinear extension of Fama-French/IPCA. IC ~0.02–0.03. → 06

**Confusion matrix** — Classification result table (TP/FP/TN/FN); must be inspected over raw hit-rate because rare event labels make accuracy a lie (class imbalance). → 05

**Connors RSI** — Short-period RSI variant; a top mean-reversion technique. → 02, 03

**Conservation of capital** — The trend-follower's creed: let profits run, cut losses; preserving the fat tail of big winners is essential to expectancy. → 02

**CPPI (Constant Proportion Portfolio Insurance)** — Dynamically lever a strategy toward zero as it loses; used to keep losing pairs/strategies alive in a stable of births/deaths. → 02

**Cross-sectional vs time-series** — Cross-sectional = rank a *pool* of assets each date (relative momentum, value); time-series = a signal from one asset's own history (absolute momentum, AR reversion). FF factors predict OOS only cross-sectionally. → 02, 04

**Curve-fitting** — See *overfitting*. → 07

**Custom loss function (ML)** — Replacing a generic objective (MSE/cross-entropy) with one aligned to the trading goal — e.g. penalizing wrong-sign forecasts, weighting by economic P&L, or maximizing a Sharpe-like criterion — so the model optimizes what actually makes money, not statistical fit (Coqueret-Guida). → 06

## D

**Dark pool** — A venue that does not display quotes; executes at the NBBO midprice (saves half-spread), uses pro-rata priority, and emits no order-flow signal. >40 for US stocks. Risks: midprice latency-arb, leakage. → 01, 09

**Data-snooping** — Reusing one dataset repeatedly for selection (White 2000); inflates false positives — the biggest statistical risk. Fix: report number of trials, control familywise error. → 07

**decay_linear** — Kakushadze operator: a linearly-weighted moving average over d days (weights d, d−1, …, 1, normalized; recent = heavier). → 04, 10

**Deflated / Probabilistic Sharpe Ratio (Bailey-López de Prado)** — Adjusts Sharpe significance for multiple testing, non-normal returns, and short samples; applies a haircut growing with the number of trials. 2 yrs daily ≈ 7 strategies; 5 yrs ≈ 45. → 07

**Delta / Delay** — Kakushadze operators: delta(x,d) = x_today − delay(x,d) (the d-day change); delay(x,d) = x's value d days ago. → 04, 10

**Delta (option, Δ)** — First-order spot sensitivity Δ = ∂V/∂S; the hedge ratio (shares per option). Call Δ = N(d₁)∈(0,1), put Δ = N(d₁)−1∈(−1,0). → 13

**Delta hedging** — Holding −Δ shares against an option to neutralize first-order spot risk; rebalanced as Δ drifts. The variance-vs-transaction-cost dilemma: more frequent hedging cuts variance but bleeds the P&L left via costs (and doesn't change fair value). → 13

**Discounted cash flow (DCF)** — Intrinsic valuation discounting free cash flow to the firm at the WACC over an explicit horizon plus a continuing value: enterprise value = Σ FCFF/(1+WACC)^t + CV/(1+WACC)^T; equity value = EV − net debt. For a quant the point is *computing the inputs* (they are the factor building blocks). → 14

**Dispersion trading** — Sell index vol, buy single-stock vol — a bet that implied correlation is too high; profitable because the index variance premium is largely a *correlation* premium. Index variance ≈ Σwᵢ²σᵢ² + Σ_(i≠j)wᵢwⱼρᵢⱼσᵢσⱼ, so dispersion isolates the ρ term. → 13

**Depth** — A liquidity facet: the cost of trading *large* size, supplied by value traders; the key price-impact indicator. → 01

**Disposition effect** — Loss aversion in action: cutting winners early and riding losers hoping for recovery — the single most common emotional bias. Countermeasure: automated stops/rule-defined exits. → 12

**Dogs of the Dow** — Buy the 10 highest-yield Dow stocks Jan 1, hold 1 yr (~10.8%/yr 1992–2011); "Small Dogs" = lowest-priced 5. → 02

**Dollar bars** — See *bar*. Aggregate by price×volume; robust to price-level changes and splits. → 10

**Dollar-neutral** — Σ(long $) = Σ(short $); use scale(x) so Σ|w| = 1. A self-financing book — don't subtract the risk-free rate from its Sharpe. → 04, 07

**Donchian channel** — Channel breakout: 4-Week Rule (break of prior 4 weeks' high/low) or 20/40 channel (buy >40-day high, exit <20-day low; basis of the Turtles). → 02

**Drawdown (max)** — Current equity vs the prior high-watermark; max drawdown = largest peak-to-trough (trough must follow peak); max-drawdown *duration* = longest recovery time. (trough−peak)/peak. → 07, 08

**DRL (deep reinforcement learning)** — RL with deep value/policy networks (DQN/DDQN) as a trading agent; interactive/online/goal-directed but overfits hard at single-stock scope. → 06

**Durbin-Watson** — Autocorrelation statistic d∈[0,4]: ≈2 none, <2 positive (trend persistence), >2 negative. → 07

## E

**ECN (Electronic Communication Network)** — An order-driven electronic venue; pays maker rebates funded by takers. Resting limit orders at the NBBO suffer adverse selection. → 01, 09

**Economic profit (EVA)** — The cleanest one-period value-creation measure: EVA = Invested Capital·(ROIC − WACC) = NOPAT − WACC·Invested Capital. A firm creates value only when ROIC > WACC; a *sustained* positive spread is the accounting fingerprint of a moat (a slow-decaying quality factor). → 14

**Effective spread** — 2 × TradeSign × (TradePrice − midpoint_at_trade); the least-noisy cost estimator, best for small retail orders, but underestimates split-order cost. → 09

**Enterprise value (EV)** — The value of the whole operating business: EV = market cap + total debt − cash (≈ equity + net debt). Capital-structure-neutral, so EV-based multiples compare across firms with different leverage better than price-based ones. → 14

**EV/EBITDA** — (mkt cap + total debt − cash)/EBITDA; capital-structure-neutral, beats P/E for cross-company comparison and one of the strongest empirical value factors (Tortoriello Q1 +5.3%/Q5 −4.9%, Sharpe 0.84). Koller prefers EV/EBITA on forward, normalized earnings. → 14

**Extreme value theory (EVT)** — Models the *tail* directly rather than the whole distribution: block-maxima (GEV) or peaks-over-threshold (generalized Pareto) fits, with tail index 1/ξ; used for fat-tailed VaR/ES where Normal/historical methods understate the wings (fat-tailed equities are Fréchet). → 08

**Efficiency Ratio (ER)** — |C − Cₙ| ÷ Σ|Cᵢ − Cᵢ₋₁| (net move ÷ sum of individual moves); 1 = pure trend, 0 = pure noise. The smoothing input to KAMA. → 03, 10

**Efficient trading frontier** — The locus of minimum-cost-variance execution schedules per expected cost (Almgren-Chriss); each point is the optimal schedule for a chosen risk-aversion λ. → 09

**Eigenportfolio** — PCA on the *correlation* matrix of normalized returns; each top PC, standardized to sum-1 weights, is a portfolio. PC1 tracks the market; higher PCs isolate themes. → 04

**Elastic Net** — Regularized regression blending L1 (Lasso) + L2 (Ridge) penalties; useful when p ≫ n. → 05

**EMA (exponential moving average)** — Eₜ = Eₜ₋₁ + sc·(Pₜ − Eₜ₋₁), sc = 2/(n+1); front-weights recent data and never fully drops old data, so it reacts faster than an SMA and doesn't double-jump. → 03

**Embargo** — After purging, also drop training samples immediately *after* a test period to kill leakage from serial correlation. → 07

**Epps effect** — Under asynchronous trading, measured correlations vanish as the sampling interval shrinks; a high-frequency data pitfall. → 10

**Equal Risk Contribution (ERC) / risk parity** — Weights chosen so every asset contributes the *same* marginal risk to the portfolio (wᵢ·(Σw)ᵢ equal across i); a long-only, leverage-friendly allocator that needs no return forecasts but can cause contagion on vol spikes. See also *risk parity*. → 04, 08

**EV/EBIT (acquirer's multiple)** — (mkt cap + total debt − cash)/EBIT; Greenblatt's "acquirer's multiple" and the value half of the Magic Formula — the cheaper, the better. Gray & Carlisle find EV/EBIT the single most robust value signal, edging out EV/EBITDA, B/P and E/P. → 14

**Event-driven backtester** — An explicit loop where one bar = one event (MARKET/SIGNAL/ORDER/FILL via an event queue); drip-feeds data to avoid look-ahead and reuses code for live trading. Slower/more bug-prone than vectorized. → 07, 11

**Expectancy** — E(X) = Σpᵢxᵢ; a true edge means Σ(winner P&L) > Σ(loser P&L) over a large sample. → 07, 12

**Expected Shortfall (ES / CVaR)** — Conditional mean loss beyond a quantile; replaces VaR/variance for heavy-tailed returns (captures tail magnitude VaR ignores). → 08

**Exponential regression slope (volatility-adjusted momentum, Clenow)** — Clenow's *Stocks on the Move* ranking: fit an exponential regression (OLS on log price) over ~90 days, annualize the slope, and multiply by R² to penalize choppiness — momentum measured in compounding terms and adjusted for fit quality. Buy the top-ranked names above their 100-day MA. → 02

## F

**Factor model** — Decomposes returns into common factor exposures + idiosyncratic risk; supplies the covariance Σ the optimizer needs and attributes performance to skill vs factor tilt. Statistical (PCA), heterotic, or fundamental. → 04, 08

**Failed breakout** — A breakout that fails to follow through (spring/upthrust); one of the highest-probability reversal setups — trade in the opposite direction, stop just beyond the failed extreme. → 02, 03

**Fama-French / Carhart** — FF3: excess return loads on market β, size (SMB), value (HML). FF5 adds RMW (profitability) and CMA (investment); Carhart adds momentum (MOM). Exposures estimated by rolling OLS. → 04, 08

**Fama-MacBeth** — Two-stage regression estimating factor risk premia (time-series betas, then cross-sectional regressions). → 08

**Fill-or-kill (FOK)** — Fill the *entire* order immediately or cancel. → 01

**Fixed-fractional sizing** — Risk a constant fraction (≤1–2%) of equity per trade; shares = (max $ risk) ÷ (entry − stop). Lets you trade any setup regardless of stop width. → 08

**FOMO (fear of missing out)** — Drives overtrading; countermeasure: rate each trade on a FOMO scale and skip if >50% of the urge is fear-of-missing-out. → 12

**Forecast diversification multiplier (FDM)** — Carver's scalar (>1) applied to a weighted-average combined forecast to restore it to full target risk after diversification across rule variations shrank its magnitude; the combined forecast is re-capped at ±20 afterward. → 08

**Forward volatility** — The volatility implied for the period *between* two future dates, backed out of two expiries so that the near and forward variances compound to the far one: σ_fwd² = (σ_far²·T_far − σ_near²·T_near)/(T_far − T_near). What a calendar spread actually trades. → 13

**Fractional differentiation** — De Prado's method differencing by a fractional order (e.g. 0.20–0.48) to make data stationary *while preserving long-term memory*; verify with ADF. Fixed-Width Window FracDiff (FFD) applies one fixed weight vector to remove the expanding-window's drift. → 10

**Free cash flow (FCF)** — The cash thrown off after funding reinvestment: FCFF = NOPAT + D&A − ΔInvested Capital = NOPAT − net investment; the factor-work proxy is FCF = operating cash flow − capex. The cleanest, hardest-to-manipulate cash-based value input. → 14

**FCF yield (FCF/price)** — (12-mo operating cash flow − capex)/market cap; the cleanest cash-based value signal and Tortoriello's "king of valuation" (Q1 +5.6%/Q5 −4.5%, Sharpe 0.78), lacking the post-2003 decay of other cash factors. → 14

**Frog-in-the-pan (FIP)** — A momentum-quality filter: a smooth, gradual (low-FIP) price ascent under-reacts and continues, whereas a jumpy one is more likely to reverse; used to keep the smoothest half of a momentum decile (Gray-Vogel). → 04

**Fundamental factor model** — Treats factor exposures β as *directly observable* (e.g. the B/P read off statements) and estimates the factor premium f by a pooled cross-sectional/panel regression r_(it) = α + β_(it)'·f + ε_(it); the mirror image of the economic (time-series-β) factor model. → 14, 04

**Front-running** — Detecting and trading ahead of a large order; the reason large traders hide size (icebergs, time-slicing). → 01

**Fundamental law of active management** — IR ≈ IC · √breadth: performance scales with skill (IC) times the square root of independent bets. Why combining many weak, uncorrelated signals beats one strong one. → 04, 02, 05

## G

**GAN / TimeGAN** — Generative adversarial nets for synthetic financial series (generator vs discriminator); TimeGAN adds reconstruction + supervised + moment losses. Evaluate on diversity, fidelity, usefulness (TSTR). Training is unstable. → 06

**Gamma (Γ)** — Second-order spot sensitivity Γ = ∂²V/∂S² (curvature of Δ); long options are long gamma. ATM gamma peaks near expiry, OTM gamma peaks far from it. For a *book* gamma is range-dependent — measure up-/down-gamma over a real spot range. → 13

**Gamma-theta P&L identity** — The heart of options trading: a delta-hedged book has Θ = −½·Γ·σ²·S² at fair vol, so theta (rent) and gamma offset exactly. Define alpha = Θ/Γ (cost of holding $1 of gamma), which is ~invariant to time-to-expiry at flat vol — so "selling short-dated options to capture more decay" is a fallacy. A delta-hedged straddle profits when *realized* vol exceeds the *implied* vol paid. → 13

**GARCH** — Conditional-variance model σ²ₜ = ω + Σαᵢσ²ₜ₋ᵢ + Σβᵢr²ₜ₋ᵢ for volatility clustering; pick (p,q) by BIC. EGARCH captures the asymmetric leverage effect. → 03, 08

**Garman-Klass** — A realized-vol estimator adding the open and close to the high-low range; more efficient than close-to-close but biased by overnight jumps and drift. → 13

**Glosten-Harris** — Order-flow regression decomposing the spread into a permanent (adverse-selection, ∝ size) part and a transitory (order-processing) part. → 01, 09

**Glosten-Milgrom** — Adverse-selection spread model: with informed probability P and value V±E, Ask = V+P·E, Bid = V−P·E, so the adverse-selection component = 2·P·E. → 01

**Golden / Death Cross** — 50-day MA crossing the 200-day MA (golden = up, death/black = down). → 02, 03

**Gradient boosting** — Sequential tree ensemble fitting residuals; the best of the tree family. Implementations: XGBoost, LightGBM, CatBoost. → 05

**Gross profitability (GPA)** — Novy-Marx's quality factor: gross profit ÷ total assets = (revenue − COGS)/assets. The "cleanest" profitability measure (least manipulated, highest up the income statement); high-GPA firms earn a persistent premium and it pairs naturally with value. → 14

## H

**Half-life** — In an OU/AR(1) mean-reverting process, the expected time for a deviation to decay halfway to the mean; sets the natural holding period. → 02

**Heterotic risk model (Kakushadze)** — A hybrid risk model: cluster the universe by fundamental industry classification (e.g. BICS), build the factor covariance *within* that clustering, and combine with statistical factors to stabilize PCA's noisy off-diagonals. → 04

**Hidden Markov Model (HMM, regime)** — Unsupervised model of hidden states (e.g. bull/bear, low-/high-vol) with transition matrix T and emission matrix E, trained via EM, decoded via Viterbi. Used as a risk-off regime overlay (cuts maxDD ~56%→24%). → 05, 02, 08

**Hierarchical Risk Parity (HRP, Prado)** — Avoids unstable Σ⁻¹ inversion: distance d=√((1−corr)/2), single-linkage clustering to reorder assets, then top-down recursive bisection allocating inverse-variance weights. Robust but not always best. → 04, 05

**Hit rate / accuracy** — Correct directional predictions ÷ total; ≠ profit (above-50% routinely loses to costs; sub-50% can win on big moves). World-class intraday traders win barely >50%. → 05, 07

**Hurst exponent** — Tradability statistic: H<0.5 mean-reverting, =0.5 GBM/random walk, >0.5 trending. → 07

## I

**Iceberg / hidden order** — Displays only a small (ideally randomized) slice of true size; loses display precedence on the hidden portion. The main avoidable execution cost is leaking size. → 01, 09

**Ichimoku Cloud** — Multi-line trend system (Tenkan 9, Kijun 26, Senkou A/B, Chikou); the cloud is a long-term filter — trade only in cloud direction. → 02

**Implied volatility (IV)** — The σ that makes BSM match an option's market price; a forward-looking, risk-neutral expectation. Plotted against strike and maturity it gives the volatility surface, and systematically exceeds subsequent realized vol on equity indices (the variance risk premium). → 13

**Information-driven bars** — De Prado's alternative to time bars: tick, volume, or dollar bars (sample per N transactions, traded volume, or price×volume) and *imbalance* bars (close a bar when signed order-flow imbalance |θ_T| = Σbₜ exceeds its expectation). Returns are closer to IID/stationary, and bars are emitted when informed trading arrives. → 10

**Implementation shortfall (IS)** — Perold's "paper portfolio" cost vs the **decision-time midpoint**: filled_size×(avg_price − decision_mid) + unfilled_size×(current − decision_price). The best estimator when data is available (immune to split/gaming bias); also an execution algo. → 09

**indneutralize** — Kakushadze operator: cross-sectionally demean x within an industry/sector group g so the feature carries no net group exposure. → 04, 10

**Information Coefficient (IC)** — Spearman rank correlation between a factor's predictions and realized forward returns, averaged per period. 0.05–0.10 is meaningful for factors; daily ML ICs of 0.01–0.03 are normal. → 04, 05

**Information Ratio (IR)** — Sharpe measured against a *benchmark* rather than the risk-free rate: (μ − μ_B)/σ_(r−r_B). Linked to skill by IR ≈ IC·√breadth. → 04, 08

**Instrument diversification multiplier (IDM)** — Carver's portfolio-level scalar (>1) that levers a multi-instrument book back up to its target risk after the imperfect correlation between instruments lowered realized portfolio vol; IDM = 1/√(w′ρw), the analogue of the FDM applied across instruments rather than rules. → 08

**Invested capital** — Capital deployed in operations: operating working capital + net PP&E + net other operating assets (≡ total debt + equity − non-operating assets); excludes excess cash. Tortoriello's ratio version: common equity + LT debt + preferred + minority interest. The denominator of ROIC. → 14

**IOC (immediate-or-cancel)** — Fill what's available now, cancel the rest; used (with limit/market) to avoid resting and thus adverse selection. → 01, 09

**Iron condor** — A defined-risk short-vol structure: sell an OTM put spread and an OTM call spread (four strikes); collect premium while spot stays inside the body, capped loss in the wings. A range-bound bet that realized vol stays below implied. → 13

**I-Star (Kissell-Glantz)** — The practitioner pre-trade market-impact model: instantaneous impact of an order of size Q is a power law in size-relative-to-liquidity scaled by volatility (I* = a1·(Q/ADV)^a2·σ^a3; published a1≈700, a2≈0.55, a3≈0.71), then split into permanent (∝ total size) and temporary (∝ participation rate POV) parts. Constants must be re-fit to your own fills. → 09

**ISO (intermarket sweep order)** — Order exploiting the SIP-vs-direct-feed lag (~0.5 ms) for hide-and-light edges. → 01

## J

**Johansen test** — A multivariate cointegration test (eigenvalue/trace statistics) that finds *how many* independent cointegrating relationships exist among ≥2 non-stationary series and returns the cointegrating vectors — generalizing the two-asset CADF to baskets and yielding the stationary hedge portfolio directly. → 07

## K

**Kakushadze operators** — A formulaic-alpha grammar over OHLCV/vwap/cap/returns: rank, ts_rank, delta, delay, decay_linear, correlation, covariance, scale, signedpower, ts_min/ts_max/ts_argmax, indneutralize, etc. — a reusable feature DSL. → 10, 04

**Kalman filter** — Online estimator treating a hedge ratio (and offset) as a hidden time-varying state; preferred over rolling OLS for pairs (no lookback free parameter). Long the spread when forecast error e_t < −√Q_t. → 02, 05

**KAMA (Kaufman Adaptive Moving Average)** — KAMAₜ = KAMAₜ₋₁ + sc²·(C−KAMAₜ₋₁) with sc driven by the Efficiency Ratio; freezes in noise, speeds in trend. Needs a filter before signalling. → 03

**Keltner channel** — MA of typical price (avg H,L,C) ± MA of bar ranges; better in noisy markets, worse in trendy. → 03

**Kelly criterion** — Growth-optimal bet fraction/leverage: continuous form f* = (μ−r)/σ² (excess return ÷ variance; can exceed 1). Multi-asset F* = C⁻¹M. Max growth g = r + S²/2. **Always use a fraction (half-Kelly)** since full Kelly assumes Gaussian/constant moments. → 08

**Key reversal day** — Uptrend over n days AND today is the highest of n AND a lower low AND a lower close; filter to days where TR > 1.5× the 20-day avg TR. → 03

**KNN (k-nearest neighbors)** — Nonparametric, instance-based predictor (no retrain); k≈√(sample size), weight by 1/distance; degrades in high dimensions. → 05

**KPSS test** — Stationarity test with null = stationary (complements ADF; detects stationarity in trending series). → 10

**Kyle's λ** — Price impact per unit of signed order flow: regress Δp on signed volume bₜ·Vₜ; the slope λ is the impact and λ⁻¹ a direct measure of market depth (larger λ = more fragile). Central liquidity measure and a predictive ML feature; cousins are Amihud's and Hasbrouck's λ. → 01

**Kurtosis** — Fat-tailedness of returns; daily-return kurtosis >6–8 in a backtest ⇒ probably overfit (too many same-size winners). → 07

## L

**Lasso (L1)** — Regularized regression doing simultaneous variable selection + shrinkage; essential when p ≫ n. → 05

**Lee-Ready** — Trade-side classification for TCA: trade closer to the bid → seller-initiated, closer to ask → buyer-initiated, at midpoint → use the last price change. Overstates cost; mishandles split fills. → 01

**Ledoit-Wolf shrinkage** — Covariance regularization Σ̂ = δ̂F̂ + (1−δ̂)S toward a structured target F̂, stabilizing the ill-conditioned sample matrix. → 04

**Leverage effect** — Volatility rises asymmetrically after price drops; captured by EGARCH. In equities, percentage volatility is *inverse* to price (low-priced stocks are relatively more volatile). → 03, 08

**Limit order** — A price-conditional order (trade only at the limit or better); provides liquidity but bears non-execution and adverse-selection risk. → 01

**Limit order book (LOB)** — The queue of passive bids/offers ranked by precedence (price → time → display → size → public-order). L1 = best bid/ask; L2 = per-market-maker depth; L3 = enter/modify quotes. → 01, 10

**Look-ahead bias** — Using data not available at decision time (off-by-one bugs, full-sample regression coefficients, using a bar's H/L/C during that bar). The single most expensive backtest bug; fix by lagging signals and the truncate-and-compare test. → 07

**Loss aversion** — Losses hurt ~2× as much as equivalent gains; drives the disposition effect. → 12

## M

**MACD** — (12-EMA − 26-EMA); signal = 9-EMA of MACD; histogram = MACD − signal. Used for trend, timing, and divergence. **Modified MACD (Grimes)** = SMA(3)−SMA(10), signal SMA(16), no histogram. → 03, 02

**Magic Formula (Greenblatt)** — Rank the universe on two metrics — earnings yield (EBIT/EV, cheapness) and return on capital (EBIT/(net WC + net fixed assets), quality) — sum the ranks, and buy the top names. The minimalist "quality + value" combo that Quantitative Value generalizes and stress-tests. → 14

**MAMA / FAMA (Ehlers)** — Adaptive MAs with α from Hilbert-transform phase rate-of-change (clamped 2–19 days); MAMA×FAMA crossover = signal; trades less, more reliably, than VIDYA. → 03

**Market impact** — The price move your own order causes; splits into **temporary** (transitory bid/ask bounce, recovers) and **permanent** (adverse-selection, random-walk, the larger share). Rises with size, falls with liquidity. → 09

**Market making** — Supplying immediacy via continuous two-sided quotes, profiting from the spread while bearing inventory and adverse-selection risk. See Avellaneda-Stoikov. → 01, 09

**Market order** — Execute immediately at best available; *walks the book* if size > quote. Crosses the spread, pays immediacy, no price control. → 01

**Marketable limit order** — A limit priced at/through the opposite quote; fills immediately like a market order but caps runaway slippage. The pragmatic retail default. → 01, 09

**Market Profile (Steidlmayer)** — Frequency distribution of intraday price using 30-min TPO letters; value area = 70% of TPO/volume range, point of control = most-traded price. → 03

**Marčenko-Pastur / covariance denoising** — Random-Matrix-Theory denoising: eigenvalues of the empirical correlation matrix below the Marčenko-Pastur bound λ₊ are noise and are clipped/flattened, keeping only signal eigenvalues, before any Σ⁻¹/optimization (raw matrices are ill-conditioned; signal is often <⅓ of variance). De Prado prefers it to fixed-threshold and Ledoit-Wolf shrinkage. → 08, 10, 04

**MDA / MDI (feature importance)** — Tree-ensemble importance scores: Mean-Decrease-Accuracy (out-of-sample, permute a feature and measure the accuracy drop) and Mean-Decrease-Impurity (in-sample, Gini/impurity reduction at splits). Both are diluted by substitution effects among correlated features — cluster first (see *clustered feature importance*). → 05

**Max drawdown** — See *drawdown*. → 07, 08

**McGinley Dynamic** — Self-adjusting smoother MDₜ = MDₜ₋₁ + (P−MDₜ₋₁)/(k·n·(P/MDₜ₋₁)⁴). → 03

**Mean reversion** — Betting on convergence after a divergence; you provide liquidity and bear adverse selection. More prevalent than trending; the default assumption unless expected earnings changed. → 02

**Meta-labeling** — A secondary ML model that decides whether to act on a primary model's signal (sizing bet/no-bet); a de Prado labeling extension. → 05, 07

**Microprice** — A size-weighted mid that leans toward the heavier side of the book; the practical "fair value" between bid and ask. → 10

**MOO / MOC (market-on-open / -on-close)** — Execute in the opening/closing auction; the close is the highest-volume evening-up point (mark-to-market, NAV). Use the primary-exchange auction price, not the SIP print. → 01

**Momentum** — Betting an established move persists. **Time-series (absolute)** = sign of own past returns; **cross-sectional (relative)** = rank a pool, long winners/short losers (Carhart MOM = 12-month winners−losers, skipping the recent month). → 02, 04

**Moneyness** — An option's strike position relative to spot: a call is ITM if S>K, ATM if S≈K, OTM if S<K (reverse for puts). Determines the Greeks' profile (e.g. ATM vega/gamma) and where on the smile the option sits. → 13

**Monte Carlo (trade-shuffle / resampling)** — Generate many equity paths by resampling/reshuffling trades to see the *distribution* of drawdowns and recovery times (a single path suffers sample bias); also used to sample parameter combinations. → 07

**Multicollinearity** — Redundant correlated features (e.g. several similar-period RSIs, or bounded oscillators RSI/Stoch/%R/CCI); decorrelate or regularize before modeling. → 03, 10

## N

**NBBO (National Best Bid and Offer)** — The consolidated best displayed bid/ask across venues; Reg NMS Rule 611 forces marketable orders to the best protected quote. → 01

**Neutralization** — Removing unwanted exposures from the alpha: dollar-, beta-, and sector/industry-neutral, implemented as a weighted regression whose residual is the neutralized alpha. → 04, 08

**No-trade region** — Under transaction costs, the band of positions left untouched; trade only when drift exits the boundary (Samuelson-Merton / Davis-Norman). → 09

**Nested clustered optimization (NCO)** — De Prado's optimizer that tames Σ's condition number by clustering assets (ONC), optimizing *within* each cluster, then *across* the cluster-aggregates, and recombining — isolating the instability so it doesn't propagate. An alternative to mean-variance/HRP/ERC when inputs are noisy. → 04

**NOPAT (net operating profit after taxes)** — Unlevered operating profit: NOPAT = EBIT × (1 − cash operating tax rate), from reorganized statements (special/one-off items stripped). The numerator of ROIC and the starting point of FCFF. → 14

**NR4 (narrow-range 4)** — A day whose range is the smallest of the last 4 (a compression filter); raises the reliability of the subsequent breakout. → 02

## O

**OBV (On-Balance Volume)** — Cumulative volume flow indicator; used as descriptive context, not a standalone signal. → 03

**Ohlson O-score** — A logit bankruptcy-probability model (Ohlson 1980) from nine accounting inputs (size, leverage, working capital, profitability, a sign-of-net-income dummy, etc.); higher O-score = higher distress odds. A financial-strength filter complementing the Altman Z- and Piotroski F-scores. → 14

**ONC clustering (Optimal Number of Clusters)** — De Prado's correlation-matrix clustering (silhouette-optimized k-means on the correlation distance) used to count *effectively-independent* strategies for the Deflated Sharpe trial count (e.g. 6,385 backtests → 4), to cluster features for importance, and inside NCO. → 07, 05

**Opening Range Breakout (ORB)** — Fix the first hour's (or N-bar) high-low; buy above the high, sell below the low; a preceding inside day raises % profitable (compression filter). → 02

**Optimal f (Vince)** — A per-bet growth fraction (PLR·p − (1−p))/PLR, PLR = avg profit ÷ avg loss; related to but possibly more robust than Kelly. → 08

**Order-book imbalance** — Ask-vs-bid resting-size imbalance; a primary HFT feature and a root of buying/selling-pressure edges. → 10, 01

**Order-flow imbalance (OFI)** — Net signed order flow (signed *trades* or queue updates); a persistent (long-memory) driver of short-horizon returns, partly impounded via impact. Accumulated signed flow also triggers information-driven imbalance bars. → 01, 10

**Order precedence** — The LOB ranking hierarchy: price → time (FIFO) → display → size/pro-rata → public-order. Price-time rewards queue position; pro-rata rewards posting size. → 01

**OU process (Ornstein-Uhlenbeck)** — The continuous-time mean-reverting process underlying spread/pairs trading; its half-life sets the holding horizon. → 02

**Overfitting** — Fitting noise rather than signal; the cardinal sin. Cure = parsimony (Occam). Detect via kurtosis, spiky parameter surfaces, in-sample/OOS divergence. → 07

## P

**Pairs trading** — Long one asset, short a related one sharing common factors; trade the stationary spread's z-score when it dislocates (entry ±2 SD, exit within 1 SD). Canonical statistical arbitrage. → 02

**Parabolic SAR** — Wilder's always-in stop-and-reverse: SARₙₑw = SARₒₗd + AF·(EP − SARₒₗd), AF 0.02→0.20. → 03

**Parkinson** — A realized-vol estimator using only the high-low range; ~5× more efficient than close-to-close but ignores opening jumps and assumes continuous trading. → 13

**Pattern Day Trader (PDT)** — US rule requiring ≥$25k equity for margin day trading. → 08

**PCA (principal component analysis)** — Diagonalize the returns covariance; eigenvectors = factor exposures, top eigenvalues = factors. The 1st PC ≈ "the market" (~55% of variance). Factors never get stale (rolling re-estimate). → 04, 05

**PEAD (post-earnings-announcement drift) / SUE** — Momentum off a *change in expected earnings*: buy on a beat, short on a miss (underreaction). → 02

**Pegged order** — A limit whose price tracks a reference (e.g. NBBO midpoint); high latency kills reactive pegging. → 01

**Piotroski F-score** — A 0–9 fundamental-strength score awarding one point for each of nine pass/fail tests across profitability, leverage/liquidity, and operating efficiency (positive ROA, positive CFO, rising margin, accruals < income, etc.). High-F cheap stocks beat low-F ones; the quality screen that rescues a naive value sort. → 14

**Point-and-figure** — Price-only charting (box ≈ 20-day ATR, classic 3-box reversal); buy on an X above the last X-column high, sell on an O below the last O-column low. → 02

**PIN / VPIN** — Probability of Informed Trading and its volume-clock version: split flow into equal-*volume* buckets, classify buy vs sell volume (bulk-volume classification), and set VPIN = Σ|V_buy − V_sell| / Σ(V_buy + V_sell) over rolling buckets — a real-time order-flow-toxicity / adverse-selection gauge that spikes ahead of liquidity dislocations. → 10, 01

**Point-in-time data** — Data stamped with its *actual availability date* (not its as-of/report date), so research never sees information live trading wouldn't. Non-negotiable for credible backtests. → 10, 07

**Probabilistic Sharpe Ratio (PSR)** — Probability that the *true* Sharpe exceeds a benchmark SR*, correcting the observed Sharpe for sample length, skew, and kurtosis; the Deflated Sharpe is PSR with SR* set to the data-mined expected maximum. → 07

**Probability of Backtest Overfitting (PBO)** — Combinatorially-symmetric-cross-validation metric: the fraction of trials in which the in-sample-best configuration underperforms the OOS median; a high PBO flags that selection is fitting noise. → 07

**Propagator model (Bouchaud)** — A transient-impact model writing price as a convolution of past signed trades with a decaying kernel G(t) (impact decays, not permanent); no-dynamic-arbitrage requires γ+δ ≥ 1 for G∝t^(−γ), f∝v^δ. It *generates* the square-root law and the optimal (e.g. U-shaped) execution schedule. → 09

**Portfolio-construction model** — The "arbitrator" module: balances alpha, risk, and cost into a target portfolio (optimization or heuristics). The diff vs the current portfolio *is* the trades. → 11

**POV (Percentage of Volume / Participation)** — Execution algo executing a fixed % of live volume (e.g. 10–20%) to stay under the radar; completion time is uncertain. → 09

**PPO (Percentage Price Oscillator)** — (9-EMA − 26-EMA)/26-EMA; a scale-free (percentage) MACD comparable across stocks. → 03

**Profit factor** — Gross profit ÷ gross loss (>1 profitable). → 07

**Pullback trade** — Enter on a low-volume pullback in the direction of the higher-timeframe trend; enter only when momentum resumes and a bar closes outside the trendline. Embrace losing the first try; the second entry is higher-probability. → 02

**Purged cross-validation** — CV that drops training points whose label/evaluation windows overlap a validation point-in-time, killing leakage from overlapping labels (López de Prado). → 07

**Put-call parity** — The European no-arbitrage link C + K·e^(−rT) = P + S₀ (use S₀·e^(−qT) with dividend yield q); ties calls, puts, the underlying and a bond so any one can be synthesized from the others, and forces a put and call at the same strike to share one implied vol. → 13

**Pyramiding** — Adding to a winning position: upright pyramid (scale-down adds, robust) vs inverted (equal adds, fragile). Add only on new-high profits; "reverse pyramids" are marketing fiction. → 08

## Q

**Quality** — Factor tilting to profitable, stable, low-leverage firms (gross profitability, ROE, accruals); protects in flight-to-quality, terrible in euphoria. → 04, 02

**Quote-driven / order-driven / brokered** — The three execution systems: quote-driven (dealers supply all liquidity), order-driven (buyers/sellers trade via precedence rules), brokered (brokers search latent liquidity). → 01

## R

**Random forest** — Bagged trees with per-split predictor subsetting (~1/3 of predictors); robust to noise, gives feature-importance scores; max_depth controls overfit (depth=10 critical in the headline intraday strategy, Sharpe 3.02). → 05

**rank** — Kakushadze's core normalizer: cross-sectional rank of x across all stocks on a day, normalized to [0,1]. → 04, 10

**Ratio spread / backspread** — Buying and selling unequal quantities at two strikes: a *ratio spread* sells more than it buys (net short options/vega, short the wings) while a *backspread* buys more than it sells (net long gamma/vega for a possible credit). A directional bet on how far spot moves *and* on vol, exploiting the smile's slope. → 13

**Realized spread** — 2 × TradeSign × (TradePrice − midpoint_post-trade); Effective − Realized ≈ the dealer's loss to informed traders (the permanent move). → 09

**Realized variance** — Sum of squared high-frequency returns; *inconsistent* under microstructure noise (RV(n)/n → 2vε), so use noise-robust estimators (TSRV, realized kernels). → 10

**Realized (historical) volatility** — Vol estimated from past returns; the estimator trades efficiency vs robustness — close-to-close (unbiased, noisy), Parkinson (high-low range), Garman-Klass (adds open/close), Yang-Zhang (handles drift and overnight gaps, the most efficient and the daily-data default). The RV leg of the IV−RV variance-risk-premium signal. → 13

**Rho (ρ)** — Option sensitivity to the interest rate, ρ = ∂V/∂r; usually minor for short-dated equity options. → 13

**ROIC (return on invested capital)** — NOPAT ÷ invested capital; the core of the value-driver identity (Value = f(ROIC, g, WACC)) and the quality stack. Value is created only when ROIC > WACC; a sustained spread signals a moat (Tortoriello Q1 +2.3%/Q5 −4.3%, strong in bear markets). → 14

**Regime** — A persistent market state (trending vs mean-reverting, low- vs high-volatility); strategies are regime-dependent, so condition each edge on a vol/trend regime (HMM, ADX). → 02, 07, 08

**Reinforcement learning (RL)** — Learning a policy from interaction: *state* (must be stationary features), *action* (buy/sell/hold), *reward* (return/Sharpe/−drawdown); agent maximizes discounted return. Reward design is the hardest part. → 06

**Resiliency** — A liquidity facet: how fast price recovers after *uninformed* pressure, supplied by value traders. → 01

**Ridge (L2)** — Regularized regression β̂ = (XᵀX + λI)⁻¹XᵀY; shrinks coefficients. → 05

**Risk model** — The "pessimist" module: controls unintended exposures via limits (not predictions); distinguishes compensated alpha exposures from uncompensated risk exposures. → 11, 08

**Risk of ruin** — Probability of losing the stake: equal win/loss R = ((1−A)/(1+A))^c (A = 2P−1, c = capital in units); any nonzero ruin probability drives long-run wealth to zero. → 08

**Risk parity** — Allocate capital ∝ 1/volatility (All Weather); simpler than HRP but causes contagion on vol spikes — Chan suggests equalizing maxDD/VaR instead. → 04, 08

**Risk reversal** — Long an OTM call financed by a short OTM put (or vice-versa), zero-cost when their premiums match; a directional position whose price *is* the skew (the call-vs-put IV gap), so traders quote skew in "risk-reversal" terms. → 13

**Roll model (1984)** — Recovers the spread from bid-ask bounce: observed P_i = P*_i + c·I_i, so Cov(ΔP_i, ΔP_{i−1}) = −c² and effective spread = 2√(−SCov). A microstructure artifact, not an EMH violation. → 01, 09

**RSI (Relative Strength Index, Wilder)** — RSI = 100 − 100/(1+RS), RS = AvgGain/AvgLoss over 14 days; >70 overbought, <30 oversold; divergence flags reversals. Pins at extremes in trends. → 03, 02

## S

**scale** — Kakushadze operator rescaling x so Σ|x| = a (default 1); the dollar-neutralizing normalizer. → 04, 10

**Security master** — Reference data mapping ticker/SEDOL/ISIN/CUSIP to one internal ID; the backbone of a data stack. → 10

**Sharpe ratio** — mean(excess return) ÷ SD(excess return), annualized × √N_T (daily → ×√252; hourly NYSE → ×√1638). <1 not viable standalone; >2 ⇒ profitable most months; >3 ⇒ profitable most days. → 07, 04, 08

**signedpower** — Kakushadze operator sign(x)·|x|^a; preserves sign while raising magnitude to power a. → 10

**SHAP** — Model-agnostic per-feature attribution for explaining individual predictions and global impact in tree ensembles; used to reject leakage-driven "features." → 05

**Slippage** — The price difference between signal and fill (on average a cost); largest for fast directional/breakout systems (buying new highs). ≈ bid-ask (S&P ~1 tick). → 09, 07

**Smart order routing (SOR)** — Routes child orders across fragmented venues for liquidity/fee/anonymity ("sweeping the market"); reliability is load-bearing (a dropped connection risks double fills or an unhedged leg). → 01, 09

**SMA (simple moving average)** — (Pᵢ + … + Pᵢ₋ₙ₊₁)/n; blind outside its window and jumps twice per large event. Crossover is the canonical trend filter but ineffective standalone on indices. → 03

**SNOA (scaled net operating assets)** — Net operating assets ÷ total assets = (operating assets − operating liabilities)/assets; a balance-sheet bloat / earnings-quality red flag (Hirshleifer et al.) — high SNOA predicts low future returns. Part of the Quantitative Value quality and manipulation screen. → 14

**Sortino ratio** — Excess return ÷ downside deviation (vs a MAR threshold); penalizes only downside volatility. → 07, 08

**Spread (3 components)** — See *bid-ask spread*: order-processing, inventory, adverse-selection. → 01

**Square-root impact law** — Impact ≈ Y·σ·√(Q/ADV): market impact scales with the square root of order size relative to liquidity; Y must be fit to your own fills. → 09

**Stationarity** — Statistical properties constant over time; second-order stationary = autocovariance depends only on lag. The precondition for most models; diagnose via ACF, test with ADF/KPSS. → 10

**Statistical arbitrage** — Exploiting mean-reverting mispricings via a market/factor-neutral book: score securities on composite signals, combine with a risk model. Pairs trading is the canonical form. → 02

**Sticky-strike vs sticky-delta** — Two rules for how the smile moves with spot: *sticky-strike* (sticky-by-moneyness) keeps each strike's IV fixed as spot moves; *sticky-delta* (sticky-moneyness) keeps IV fixed per delta so the whole smile slides with spot. The choice changes a hedge's effective delta (skew adds vanna). → 13

**Stochastic oscillator (Lane)** — %K = 100·(C − Lₙ)/(Hₙ − Lₙ); %D = MA of %K; bounded 0–100, overbought/oversold re-cross at 25/75. Never use a timing rule to exit. → 03

**Stop order** — Dormant until price trades through a trigger, then becomes a **market** order (no price guarantee, can gap past the level). **Stop-limit** becomes a limit (avoids slippage but risks non-execution). → 01

**Stop-loss / trailing stop** — A risk-control exit set at entry outside the noise level; trailing types: fixed-%, volatility-based (high − k×ATR), or Kase Dev-Stop. Help in trending regimes, hurt in mean-reverting ones. → 08

**Straddle** — Long (or short) a call and a put at the *same* strike and expiry; a pure, direction-neutral bet on the *magnitude* of the move — long straddle profits if realized vol beats the implied vol paid (max ATM gamma/vega), short straddle harvests the variance premium. → 13

**Strangle** — Like a straddle but with *different* OTM strikes (call above, put below); cheaper, needs a bigger move to pay, and is the workhorse for trading the wings / vol level with less theta than a straddle. → 13

**STF (Setup → Trigger → Follow-through)** — The universal discretionary-trade structure; a high-accuracy pattern is useless without a trigger and an exit. → 02

**SUE (Standardized Unexpected Earnings)** — The earnings-surprise measure driving PEAD. → 02

**Survivorship bias** — Testing only on assets that survived; badly inflates "buy cheap"/value strategies (toy example: −42% real vs +388% survivor-only). Fix with delisted-inclusive point-in-time data and historical index composition. → 07, 10

**SVM / SVR (support vector machine/regression)** — Maximal-margin → soft-margin (budget C) → kernel trick (linear/poly/RBF); C is the bias-variance knob. Strong in high dimensions (text/sentiment); the linear kernel won on SPY because the relationship was genuinely linear. → 05

**Swing filter** — A threshold (best as % of price) defining a new swing high/low; a new upswing starts when price reverses from the low by ≥ the filter. No lag, no action in sideways markets. → 02

## T

**Tear sheet (Alphalens)** — Standard factor-evaluation output: mean return by quantile (want a monotonic spread), IC, IC decay, turnover, sector breakdown. → 04

**Theta (Θ)** — Option time decay, Θ = ∂V/∂t (the "rent" paid to own gamma); long options pay theta. At fair vol it offsets gamma exactly: Θ = −½·Γ·σ²·S² (the gamma-theta identity). → 13

**Tick size** — The minimum price increment; a first-order structural variable. Too small weakens time precedence and kills displayed size (post-2001 decimalization); too large makes price-improvement expensive. → 01

**Time stop** — Exit after N bars if the move hasn't materialized; core to the asymmetric-payoff school (trade must "work immediately"). → 08

**Timing risk** — The variance of execution cost from price moving while you work an order; reduced by aggressive schedules, increased by slow ones — the heart of optimal execution. → 09

**Toxicity (flow)** — "Hot" flow whose prices rise after your buys / fall after your sells, marking you as informed; dealers won't pay for it. Measured as P&L(unfilled) − P&L(filled). → 09

**Transaction-cost model** — The "frugal accountant" module: *describes* cost (it doesn't minimize it); portfolio construction decides if alpha justifies the cost. → 11, 09

**Triple-barrier labeling** — De Prado's path-dependent labels: profit-take, stop-loss, and time barriers define the label by whichever is hit first. → 07, 10

**TRIN (Arms Index)** — (advancing/declining stocks)/(up/down volume); <1 bullish; a real-time breadth/sentiment gauge. → 03

**TRIX** — Triple-EMA of ln(price); buy when it rises 2 consecutive days; a smoothed momentum trigger. → 02, 03

**ts_rank / ts_argmax** — Kakushadze time-series operators: ts_rank(x,d) = rank of today's x within its trailing-d-day window; ts_argmax(x,d) = the day index of the d-day max. → 04, 10

**Turtle system** — Donchian breakout system (Dennis/Eckhardt): S1 = 20-day breakout / 10-day exit (skip if prior won); S2 = 55-day / 20-day; ATR-based unit sizing, 2L stop, add a unit every +L, cut size 20% per 10% drawdown. → 02

**Turnover** — Share of assets entering/leaving a quantile each period; a direct proxy for trading cost. High turnover threatens net returns; Kakushadze alphas hold 0.6–6.4 days. → 04

**TWAP (Time-Weighted Average Price)** — Execution algo splitting the order *evenly* across equal time slices; signals "uninformed" but ignores the volume profile. Vulnerable to sniffers (counter with fuzzy spacing/RNG). → 09

## U

**UHOB (Unusual Hold on the Bid)** — A buyer repeatedly taking prints at one price and refusing to drop the bid → foreshadows a large hidden order; step in front, stop just below. → 02

**Ulcer Index** — Downside-risk measure based on the semi-variance of drawdowns (depth and duration). → 08

## V

**Value (factor)** — Long cheap / short rich on fundamentals (B/P, E/P; invert ratios to yields); the classic market-neutral long-short. Useless on SPX large-caps, works on small-caps. → 04, 02

**Value area** — The price range containing 70% of TPO/volume in Market Profile; point of control = most-traded price. → 03

**Value driver** — In Koller's intrinsic-valuation logic, the inputs that determine value: ROIC, growth g, and WACC (Value = f(ROIC, g, WACC)); the key value-driver formula is Value = NOPAT₁·(1 − g/ROIC)/(WACC − g), so higher ROIC and (only if ROIC>WACC) higher growth lift value. → 14

**VaR (Value-at-Risk)** — Loss not exceeded with probability 1−α: P(L ≥ VaR) = α. Three methods: **parametric** (Normal fit), **historical** (sort past returns, take the quantile), **Monte Carlo** (empirical quantile of simulated paths). Understates fat-tailed risk; never use alone. → 08

**VAR / VEC (vector autoregression / error-correction)** — Multivariate dynamics for baskets; VEC error-correction signs reveal which names mean-revert. → 02

**Vanna** — Cross Greek ∂²V/∂S∂σ: how delta drifts as vol changes (equivalently how vega changes with spot). Matters once vol co-moves with spot (skew), and underlies Taleb's *shadow gamma*. → 13

**Variance ratio test (Lo-MacKinlay)** — A random-walk/mean-reversion test comparing the variance of q-period returns to q× the 1-period variance: VR(q) = Var(r_q)/(q·Var(r₁)). VR≈1 = random walk, <1 = mean-reverting, >1 = trending; the homoscedasticity/heteroscedasticity z-statistics give significance. A more powerful tradability gauge than a raw Hurst estimate. → 07

**Variance risk premium (VRP)** — Implied vol systematically exceeds subsequent realized vol, so IV ≈ expected vol + a positive premium; the standard proxy is the IV−RV gap (cleanest via variance swaps). The "sell insurance" carry trade — large and positive on equity *indices* (a correlation premium), with losses that cluster in crashes, so the high Sharpe hides the tail. → 13

**Variance swap** — An OTC contract paying realized variance minus a fixed strike K_var; clean, linear exposure to realized_var − K_var with no path-dependent gamma trading. The model-free way to harvest the VRP. → 13

**Vectorized backtester** — Whole-dataset NumPy/pandas array ops; concise/fast for a first test (the .shift(1) avoids look-ahead) but can't model fixed costs, indivisibility, or path-dependent state. → 07, 11

**Vega (ν)** — Option sensitivity to implied vol, ν = ∂V/∂σ; bell-shaped, max ATM. Vega-hedging neutralizes level-of-vol risk; for a book never net vegas of different maturities un-weighted (short vols react far more — weight by √(90/days)). → 13

**Vertical spread** — Long and short the same option type at *different strikes, same expiry* — a bull/bear call or put spread. Defines a capped risk/reward, cheapens the directional bet, and is the basic building block of butterflies, condors and ratio spreads; its price is mostly a play on the smile between the two strikes. → 13

**VIDYA (Chande)** — Variable-index dynamic MA; higher volatility → *slower* trend (opposite of KAMA), k = stdev(n)/stdev(m). → 03

**VIX** — The 30-day model-free implied variance of S&P 500 options (a variance-swap-style strip), quoted as annualized vol; VIX futures/options trade the level and term structure of expected vol directly. → 13

**Volatility parity / targeting (vol scalar)** — Size inversely to volatility (weights ∝ 1/σ or 1/σ²) to equalize risk, then scale the book by a **volatility scalar** = target σ ÷ forecast σ to hit a target annualized vol (~12%); deleverage above target, leverage below. → 08

**Volatility smile / skew** — The variation of implied vol across strikes at a fixed maturity. Equity indices show a persistent negative skew ("smirk") — OTM puts richer than OTM calls — driven by vega-convexity away from the money and crash-o-phobia / portfolio-insurance demand. Skew is *not* a clean risk gauge (ATM vol is). → 13

**Volatility surface** — Implied vol as a function of both strike and maturity (Dupire-Derman-Kani); deforms in orders (parallel shift, rotation, higher-order), so strike×time "squares" need a covariance treatment, not a single number. → 13

**Volatility term structure** — Implied vol as a function of maturity at fixed moneyness; usually upward-sloping in calm and inverting in stress, with short vols mean-reverting hardest. A forward-looking regime/crash-fear state variable. → 13

**Volga / vomma** — Second-order vol Greek ∂²V/∂σ²: the convexity of vega. Long OTM options are long volga; together with vol-of-vol it drives the price of the wings above BSM (fat tails). → 13

**VWAP (Volume-Weighted Average Price)** — Σ(size·price)/Σ size. As a benchmark it's easy but self-gameable (if you're most of the volume, measured cost → 0). As a signal, above VWAP = buyers in control; as an algo, slice proportional to expected volume. → 09, 03, 02

## W

**WACC (weighted average cost of capital)** — The DCF discount rate: WACC = (E/V)·kₑ + (D/V)·k_d·(1−tax), with cost of equity from CAPM kₑ = r_f + β·ERP (ERP ≈ 4–5%); use *market* weights. Value is created only above it (ROIC > WACC). Caveat: β is a poor single-stock risk proxy — substituting Price-to-Sales improves economic-profit factors. → 14

**Walk-forward analysis** — In-sample fit → next out-of-sample block → roll forward, accumulating OOS results; parallels live deployment. Uses all the data, so still reserve a final untouched OOS set; short windows bias toward fast models. → 07

**Walk-Forward Efficiency (WFE)** — Annualized OOS net profit ÷ annualized in-sample net profit: >100% = robust, ≥50% commonly accepted (expect ~half the in-sample edge live). Run ≥10 WF tests; passing earns more trust because over-fit systems fail WFA readily. Also a "system-farm" activator (trade only systems >50%). → 07

**Williams %R** — (MAXₙ − C)/(MAXₙ − MINₙ)×100; swings 0 to −100 (0 to −20 overbought, −80 to −100 oversold); leads reversals. → 03

**Winner's curse** — In liquidity provision, bidding lower against more competitors and harder-to-value names; act only on *large* mispricings. → 02

**Winsorizing** — Clipping extreme values (e.g. to [1%,99%]) before variance-sensitive steps like PCA; flag outliers via z-score (|z|>3). → 10, 04

## X

**XGBoost** — Regularized gradient boosting; generally the best of the tree family (handles missing values, parallel, feature importance). Tune n_estimators, max_depth; watch directional skew. → 05

## Y

**Yang-Zhang** — A realized-vol estimator combining overnight (close-to-open) and intraday (Rogers-Satchell) components; handles both drift and opening gaps, the most efficient of the common estimators and the default for daily equity data. → 13

## Z

**z-score** — Standardized deviation (value − mean)/σ; the spread-normalizer in pairs trading (z = (spread − rolling_mean)/rolling_std; enter at |z|≥entry, exit toward the mean) and the outlier flag (|z|>3). → 02, 10
