# 03 — Technical Analysis & Indicators
*Trading System Knowledge Base · theme T03 · equities/ETF-weighted*
*Updated: includes Aronson (evidence-based TA), Heikin-Ashi, Alligator/Gator, Carver EWMAC.*
*Updated (pass 3): added Clenow's exponential-regression-slope×R² momentum measure.*

**What this covers:** Indicator formulas (trend/smoothing, momentum/oscillators, volatility/bands, volume/flow), price patterns and market-structure concepts, all treated as quantified, backtestable **features** rather than chart-reading lore. Standard parameters, lookbacks, and overbought/oversold conventions are given alongside each formula.
**Why it matters:** Indicators are the cheapest, most liquid feature set in equities/ETFs — computable from OHLCV alone (Jansen p.194). For an ML-driven or rule-based system they supply trend, momentum, and volatility regressors. But almost none has standalone edge; the value is in (a) using them as model inputs and (b) validating them statistically rather than accepting/rejecting on faith.
**Primary sources:** Kaufman, *Trading Systems & Methods* (the formula reference); Grimes, *Art & Science of Technical Analysis* (charting discipline + Modified MACD); Aronson, *Evidence-Based Technical Analysis* (the objective/subjective divide and statistical validation); Kaabar and Jansen (TA-as-features); Carver, *Systematic Trading* and *Advanced Futures Trading Strategies* (EWMAC ladder, forecast scaling, volatility estimation); Clenow, *Following the Trend* (MA/breakout trend filters) and *Stocks on the Move* (volatility-adjusted momentum ranking — exp.-regression slope × R²); Leshik & Cralle, Bernstein, Bellafiore (*PlayBook*), Chan (*Machine Trading*), Harris, Narang (*Inside the Black Box*), Guo et al. (*Chinese Quant*); Heikin Ashi Trader / SmartMoney (*Scalping is Fun* / *Trading With Technical Trend Indicators* — low-rigor sources, used only for indicator construction and flagged where formulas are inconsistent).

---

## 1. TA as quantified features, not magic

The defensible position across every quant source: TA is a **hypothesis generator**, not gospel. Quants can statistically evaluate "TA-based" signals rather than accept/reject them emotionally (*SuccessfulAlgo* p.32; Kaabar p.143). Three framings worth internalizing:

- **Statistical foundation exists.** Moving-average rules map to finite-window generalized-likelihood-ratio (GLR) fault detection; filter rules map to CUSUM — i.e., technical rules are sequential change-point detectors with a hypothesis-testing basis (Guo et al. p.42, 54–55). Time-series analysis (ARIMA, cointegration, GARCH) is the rigorous successor to ad-hoc indicators: it brings goodness-of-fit and model selection where TA brings eyeballing (Halls-Moore p.5, 74).
- **Edges decay.** Technical trading only works if informed traders make *systematic, repeated* mistakes; opportunities erode as markets mature and others learn the pattern (Harris p.231). Humans are biologically primed to see patterns that aren't there — guard against false positives in any pattern model (Harris p.231).
- **Use as inputs, not standalone rules.** Indicators are noisy and ambiguous: in the AAPL example, RSI and Bollinger flagged "overbought" while price kept rising (Jansen p.195–196). Multi-agent and ML systems treat the indicator suite as *descriptive context, explicitly not signals* (LLMagents/ATLAS p.11–12; Kaabar p.143, 304).

**Validation mindset (Grimes).** Clarity and consistency above all: price bars must be the first thing the eye sees; indicators are supplements. Keep one identical chart layout across all markets and time frames — this enables scanning ~500 charts/day at ~1s each and trains intuition (Grimes p.29–30, 36). Use **log/semi-log scaling** for any chart with >100% price change or >2 years of data (p.30–32). Define a **Trading Time Frame (TTF)**, a Higher TF (context) and Lower TF (entry/risk), related by a factor of **3–5**; vertical distances (stops, targets) scale with **√(time-frame ratio)** — a $0.25 stop on 5-min ≈ $0.61 on 30-min (p.33–34). Operational discipline rules: score every technical level 1–10 and trade only off significant ones (≥7); weight TA more for high-beta names, which carry a built-in daily catalyst because so many trade them off levels (Bellafiore p.45–46). Sift charts with a *consistent* system for ~6 months before judging it — there is no Holy Grail chart (Bellafiore p.288, 336).

### 1a. Aronson's central lesson — objective vs subjective TA (the great divide)

The single most important framing for treating TA as features. Aronson splits all of technical analysis along a hard line (Aronson p.5, 15):

- **Objective TA** = precisely defined, repeatable procedures that emit **unambiguous positions** (long / short / neutral) from the data. **Subjective TA** = vague methods requiring private analyst interpretation, so two analysts can reach *opposite* conclusions on the same chart (p.5). Classical chart patterns, hand-drawn trendlines, Elliott Wave, Gann, and Magic-T are all subjective (p.5). Carver concurs and refuses to systematise Fibonacci, candlesticks, or Elliott waves on exactly this ground — they "can't be objectively systematised and are rarely agreed upon" (Carver ch.1).
- **Programmability is the acid test.** A method is objective *if and only if* it can be coded as a program that produces unambiguous positions; anything that can't is subjective by default (p.16). Objective methods are **backtestable, hence refutable**; subjective ones are *"not even wrong"* — meaningless, insulated from empirical challenge, taken on faith (p.6). This is the binary, backtestable-rule standard the rest of this file applies to every indicator: a usable TA signal must reduce to an objective, falsifiable rule.
- **"Obvious validity" is no validity.** Most popular TA sits where medicine sat as a faith-based folk art — claims rest on colorful narratives and cherry-picked anecdotes, not statistical evidence (p.1). Expert chartists **cannot reliably distinguish real price charts from charts generated by a random process** (p.38, 83), so chart-based intuition of "this pattern obviously works" carries no evidentiary weight. Charts have a legitimate role *only* as a source of inspiration that generates testable hypotheses; until objectively tested they are suppositions, not knowledge (p.82).
- **A profitable backtest is necessary but not sufficient.** Past success can come from luck or data-mining bias; this is why many objective methods that backtest well still fail out-of-sample (p.6). Theory is what turns an isolated, possibly-lucky result into "part of a larger cohesive picture" and makes it less likely a fluke — e.g. trend-following profits in futures framed as a risk-transfer premium paid to hedgers (p.335). TA is justifiable *only if* prices are nonrandom to some degree some of the time, and **each method must separately prove by objective evidence that it captures part of that nonrandomness** (p.331).
- **Premise check.** Popular TA's "price discounts everything" slogan is self-contradictory: if price already reflected all information it would hold no predictive information — and it is the *same* premise EMH uses to reject TA (p.332–334). A coherent, *testable* mechanism for trends comes instead from behavioral under-reaction (conservatism bias, anchoring): prices drift gradually toward the rational level new information implies rather than jumping instantly (p.333, 338–340) — the documented basis for momentum/trend features.

**The headline empirical result.** Aronson back-tested **6,402 objective TA rules** on the S&P 500 and, after correcting for **data-mining bias** (the multiple-comparisons inflation from testing thousands of rules), found **none with statistically significant out-of-sample edge** (the entire study is constructed to make this measurable, which only an objective rule allows). Practical consequence for this KB: treat every indicator as a **weak, decaying feature that must be validated under multiple-testing correction**, never as a standalone edge — see **§7**, the *To validate* checklist, and **file 07** (deflated Sharpe / Bonferroni-style corrections, holdout discipline). This is the quantitative backbone behind the "edges decay / use as inputs not rules" framing above.

### 1b. What price series actually look like (empirical stylised facts)

Why indicators are weak features in the first place — the statistical properties any TA signal is fighting against (Tsay/TQP p.12–36). These are the "ground truth" a backtested rule must beat:

- **Prices are near-martingales.** The best estimate of the future price is the current price; **linear return predictability is essentially absent** and signals correlate with future returns only *weakly* (dispersion ≫ mean prediction) (p.12). Distinguishing skill from luck takes ~`(σ/μ)²` years — ≈9 years for 15% vol / 5% return (p.13). This is the quantitative reason an indicator's apparent edge is so easily a fluke.
- **Bachelier diffusion / volatility-signature plot — the direct trend-vs-reversion test.** The variogram `V(τ) = E[(p_{t+τ}−p_t)²] = Dτ` grows *linearly* in lag for a pure random walk; the signature plot `σ(τ) = √(V(τ)/(τ·p̄²))` is **flat** for a random walk, **rises** with positive (trending) autocorrelation, and **falls** with negative (mean-reverting) autocorrelation (p.24–25). Empirically signature plots are **remarkably flat from seconds to months** (S&P E-mini decays only ~20% → only *weak* mean-reversion) — markets are neither sub- nor super-diffusive in aggregate (p.27). Implication: the trend/reversion any indicator tries to harvest is faint and horizon-dependent; *compute the signature plot before assuming a regime*.
- **Fat tails are universal.** Returns are power-law, not Gaussian; Student's-t fits with **tail exponent μ ≈ 3** across stocks, FX, rates, commodities, implied vol (p.29). A 10σ move: ~`10⁻²³` under Gaussian vs ~`4×10⁻⁴` under μ=3. Jumps `>4σ` contribute ~30% of total variance and are mostly **unrelated to news** (p.32) — so band/σ-based OB/OS thresholds (Bollinger, std-dev bands in §4) systematically understate extreme moves.
- **Volatility clustering, long memory, leverage.** `r_t = σ_t ξ_t` with IID `ξ` and `σ_t = σ_0 e^{ω_t}`; log-vol variogram `V_ω(τ) ≈ χ₀²·ln[1+min(τ,T)]`, "vol of vol" `χ₀² ≈ 0.05`, vol bursts on *all* scales (not a single-relaxation OU process) (p.30). **Leverage effect:** past *negative* returns raise future vol, but past vol gives **no directional** information (p.31). Long-ranged vol correlations also *slow* the CLT (returns stay non-Gaussian for weeks/months) (p.31). This is the empirical justification for GARCH/ATR vol features and volatility-scaled sizing — and a warning that vol, not direction, is the predictable part.
- **Excess volatility / endogeneity.** Trading activity vastly exceeds news arrival and most large jumps lack identifiable news; ARCH/Hawkes feedback models attribute **≥80% of price variance to self-referential (endogenous) effects** (p.35–36). Fundamental value only "anchors" price on multi-year scales — secondary for the short horizons most indicators operate on.

---

## 2. Trend / smoothing indicators

A moving average changes each bar only by (new price − dropped price)/n, making it nearly a momentum measure (Kaufman p.548). Choose n **out of phase** with any known cycle (n ≠ cycle length, ideally < ½ cycle) (p.549–550). Behavior matters: an **SMA** is blind outside its window and *jumps twice* per large event (when the value enters and exits the window); an **EMA** front-weights recent data and never fully drops old data, so it reacts faster and doesn't double-jump (Grimes p.146–151).

| Name | Formula | Typical params | Use / notes |
|---|---|---|---|
| SMA | MAᵢ = (Pᵢ + … + Pᵢ₋ₙ₊₁)/n | 20, 50, 100, 200; 63 ≈ qtr, 252 ≈ yr | Trend bias: P>MA bullish, P<MA bearish; golden/death cross of two SMAs (Kaabar p.143; Kaufman p.624–626) |
| EMA (exp. smoothing) | Eₜ = Eₜ₋₁ + sc·(Pₜ − Eₜ₋₁), sc∈[0,1]; sc = 2/(n+1) | 12, 26; 9/13/50 stacks | Front-loaded; old data never fully drops → 10% smoothing slower than 10-day SMA, 5% slower than 20-day (Kaufman p.565–571). ARIMA(0,1,1) ≡ simple exp. smoothing (p.523) |
| WMA (linear/step) | wᵢ = n, n−1, …, 1 over Σ; or stepped wᵢ = a·wᵢ₊₁ (a≈0.9 ≈ exponential) | n-day | Front-loaded to cut lag (Kaufman p.554–556) |
| Triangular MA | Peak weight at middle (day n/2), smallest at both ends | — | Noise reduction front+back; used for cycles; Gaussian/bell variant (Kaufman p.557–558) |
| Hull MA | 3 weighted averages over period, √period, ½period | 16 weeks | Aggressively shortens lag (Kaufman p.581) |
| KAMA (adaptive) | KAMAₜ = KAMAₜ₋₁ + sc²·(C − KAMAₜ₋₁); sc = ER·(fastSC − slowSC) + slowSC; **ER = \|C − Cₙ\| / Σ\|Cᵢ − Cᵢ₋₁\|** | fast/slow 2&30 or 3&30; ER over n≈8–10 | ER ("efficiency ratio") 1=pure trend, 0=pure noise; freezes in noise, speeds in trend. **Needs a filter** F: signal only when KAMA moves a fixed amount away from its extreme (Kaufman p.1532–38) |
| VIDYA (Chande) | VIDYAₜ = s·k·Cₜ + (1 − s·k)·VIDYAₜ₋₁; **k = stdev(n)/stdev(m)** | s=0.20 (9-day), n=9, m=30 | Higher vol → SLOWER trend (opposite logic to KAMA); apply stdev to price *changes* (Kaufman p.1539–40) |
| MAMA / FAMA (Ehlers) | α from Hilbert-Transform phase rate-of-change, clamped 0.05–0.50 (2–19 days); FAMA = MAMA of MAMA with ½ α | — | MAMA × FAMA crossover = trade signal; trades far less than VIDYA → more reliable (Kaufman p.1542–43, 1547) |
| McGinley Dynamic | MDₜ = MDₜ₋₁ + (P − MDₜ₋₁)/(k·n·(P/MDₜ₋₁)⁴) | k=0.60 | Self-adjusting smoother (Kaufman p.1551) |
| **EWMAC** (Carver) | EWMAC = EWMA(fast) − EWMA(slow); A = 2/(1+span); normalise by recent price vol for a *continuous* forecast | fast/slow span pairs 2–8/8–32 (e.g. 16/64) | Carver's core trend signal: a **continuous** crossover (not binary) — magnitude *and* sign are used, capped, then risk-scaled. Objective & systematisable; the always-objective successor to the discretionary MA cross (Carver ch.1, App.B/D) |
| **Heikin-Ashi candles** | HA-Close = avg(O,H,L,C); HA-Open = avg(prior HA-Open, prior HA-Close); HA-High/Low = extreme of (H or L, HA-Open, HA-Close) | per-bar | **Smoothed-trend candle**, not an average over n: recolours bars so *direction* reads off candle colour, *strength* off body size, *exhaustion* off wick length (small bodies = weakening, long wicks = exhaustion). Encode the standard formula; the source gives only visual behavior (LightScalp ch.5) |
| **Alligator** (Bill Williams) | 3 displaced SMAs: **Jaw = SMA(13) shifted +8**, **Teeth = SMA(8) shifted +5**, **Lips = SMA(5) shifted +3** | 13/8/5, shift 8/5/3 | Trend-state machine: lines **intertwined = "sleeping"** (no trend); **crossing = "awakening"** (possible reversal); **fanned & aligned = "eating"** (strong trend). Separation ∝ trend strength; price vs Jaw = breakout/stop reference. **Flag:** classic BW uses **SMMA on median price (H+L)/2**; LightScalp's code uses plain SMA on close — a simplification (LightScalp) |

Related smoothers: average-off (substitute prior average for oldest point), pivot-point MA (reverse linear weights going negative to cut lag), geometric MA (average of ln-price, weights low values; only over long wide-range data), standard-deviation MA, moving median (ignores extremes but lags badly through turns) (Kaufman p.553–563). **Adaptive R²** uses the correlation coefficient r² (close vs 1,2,3…) as the smoothing constant (Kaufman p.1541). **FRAMA** uses fractal dimension (Kaufman p.1544–45).

**Crossover lineage / signals:** SMA crossover is the canonical trend filter — short MA above long = positive trend (Narang p.28), traced to Brock/Lakonishok/LeBaron 1992 (Hilpisch p.88). Stacks: 3/10/21 or 9/13/50 to filter false signals (151Strategies p.51; BrokerTest p.246). It is **ineffective standalone on index data — needs a regime/vol overlay** (Halls-Moore p.466). Crossing down = "Black/death cross"; crossing up = "Golden cross" (Leshik p.118). **Parabolic SAR** (Wilder): always-in, stop-and-reverse — SARₙₑw = SARₒₗd + AF·(EP − SARₒₗd), AF starts 0.02, +0.02 each new extreme, cap 0.20 (Kaufman p.1552–54).

**Trend filters for a diversified systematic book (Clenow, *Following the Trend*).** Clenow's core engine is the simplest objective trend logic applied across a broad futures/ETF universe: trade only in the direction of a **long-term moving-average filter** (e.g. price vs a long EMA, or fast-EMA-above-slow-EMA as a regime gate) and **enter on a price breakout** (Donchian-style highest-high / lowest-low channel), sizing every position by ATR so each contributes equal risk. The edge is *not* in the indicator — almost any MA/breakout length works — but in **broad diversification, ruthless risk-parity sizing, and sitting through whipsaws**; the trend filter just keeps you on the right side of the long-run drift (Clenow, *Following the Trend*). This is the practical complement to Carver's continuous EWMAC: same objective trend premise, binary-gate vs continuous-forecast implementations. Cross-ref **file 07** (ATR sizing) and **file 08** (universe).

**Gator Oscillator** (companion to the Alligator above) = a histogram view of Alligator convergence/divergence: **top bars = |Jaw − Teeth|**, **bottom bars = −|Teeth − Lips|**. Bars near zero = sleeping; growing bars on both sides = trend accelerating ("smile"); shrinking/contracting bars = trend fading ("bite"). **Source-inconsistency flag:** LightScalp's prose/code redefine Gator as `(Jaw−Teeth)+(Teeth−Lips)` with periods 13/21/55 — internally inconsistent with its own 13/8/5 Alligator; encode the **standard** absolute-difference two-sided histogram off the 13/8/5 Alligator instead (LightScalp).

---

## 3. Momentum / oscillators

Momentum is the most basic trend tool — **M = Pₜ − Pₜ₋ₙ; true ROC = (Pₜ − Pₜ₋ₙ)/n** (Kaufman p.547). Oscillators are bounded (often 0–100) and **prone to false signals in strong trends** — they cluster at extremes while price keeps running (BrokerTest p.274–275; Jansen p.195). Already-normalized indicators (e.g., RSI) need no further volatility scaling before ML (Chan p.109).

| Name | Formula | Typical params | OB/OS convention |
|---|---|---|---|
| RSI (Wilder) | RSI = 100 − 100/(1+RS); RS = smoothed avg gain / smoothed avg \|loss\|; Wilder smoothing (prev MA×13 + today)/14 | 14 | >70 OB, <30 OS; 50-cross = weak trend; **divergence** = reversal (Kaabar p.145–46; Leshik p.119) |
| Connors RSI / short-RSI | Short-period RSI | 2 or 4 | Stronger short-term mean-reversion edge (BrokerTest p.278) |
| Stochastic %K/%D | %K = 100·(C − Lₙ)/(Hₙ − Lₙ); %D = 5-period MA of %K | 12–14, %D=5; slow %K (14,5) | Bounded 0–100; OB/OS re-cross at 25/75 (Leshik p.121; Bernstein p.31–33) |
| MACD (standard) | (12-EMA − 26-EMA); signal = 9-EMA of MACD; histogram = MACD − signal | 12, 26, 9 | Zero-line and signal crossings; divergence (BrokerTest; LLMagents) |
| **Modified MACD (Grimes)** | fast = SMA(3) − SMA(10); signal = SMA(16) of fast; **no histogram**; zero line | 3/10/16 | Fast line = distance between MAs = momentum (responds to 2nd derivative). "Fast line down" = momentum decelerating, NOT price falling. Beware ~10-bar construction *artifact* after a clean trend start (Grimes p.155–59) |
| PPO | (9-EMA − 26-EMA)/26-EMA | 9, 26 | Percentage MACD; scale-free across stocks (Leshik p.120) |
| TRIX | Triple-EMA of log price; zero-line crossings | — | Smoothed momentum entry trigger (Leshik p.120) |
| TSI / Blau double-smooth | Double-smooth of price *changes* (first differences) restores sensitivity, adds only one lag | e.g. 250d then 5d | Good long-term; scale ≠ price (Kaufman p.573–82) |
| Williams %R | (MAXₙ − C)/(MAXₙ − MINₙ)×100 | 14 | Swings 0 to −100; 0 to −20 OB, −80 to −100 OS; leads reversals (Leshik p.122) |
| ROC / Momentum | Pₙₒw − Pₙ (or %) | 28 | Divergence: price & MOM normally in sync; out-of-phase flags turns (Bernstein p.52–56) |
| **Adjusted slope (Clenow)** | annualized exp.-regression slope of ln(price) × R²: slope = SLOPE(ln P vs t); annualized = exp(slope)^250 − 1; ×RSQ(ln P, t) | 90-day window | **Volatility-adjusted, rankable momentum** — a rigorous alternative to raw ROC. R²∈[0,1] penalizes choppy/gappy advances; rewards smooth straight-line trends. Sort the whole portfolio on this (Clenow, *Stocks on the Move*, Ch. 7). See §3a |
| CCI | Bounded 0–100 oscillator | — | Momentum; false signals in strong trends (BrokerTest p.274–75) |
| DMI (Chande) | Variable-length RSI; period = INT(P/Vₜ), P=14, V = stdev(n)/avg-stdev(m) | n=5, m=10 | High vol → shorter period; use price *changes* (Kaufman p.1561) |
| Fisher Transform | Y = 0.5·ln((1+X)/(1−X)), X = position in p-period channel scaled to ±1 | trigger = 3-day MA | Sharper turns than momentum; ±1 range; good for mean reversion (Kaufman p.985). Inverse Fisher wraps RSI (p.988) |

**Adaptive momentum:** map any oscillator to a smoothing constant — M∈(0,1)→sc=M; M∈(−1,1)→\|M\|; M∈(0,100)→M/100; M∈(−100,100)→\|M/100\| (Kaufman p.1549). **ADX** recognizes trend *presence* (>18 & rising → ~95% trending in expert-system rules) but is not directional (Kaufman p.684, 1727–30).

**Oscillator-family equivalence (scalper's confirmation stack).** LightScalp pairs trend with three bounded oscillators used interchangeably for OB/OS and divergence, reinforcing the §7 redundancy warning that these are one construct: **RSI(14)** >70/<30; **Stochastic (Lane, 14,3,3)** %K = (C − Lₙ)/(Hₙ − Lₙ)×100, %D = 3-SMA of %K, >80/<20, %K-crossing-%D = signal; **Williams %R(14)** = essentially an *inverted, un-smoothed Stochastic %K* (> −20 OB, < −80 OS). Treat as confirmation/filters on a trend signal, not standalone — and decorrelate before stacking as ML features (LightScalp).

### 3a. Clenow's volatility-adjusted momentum — exponential-regression slope × R² (the rankable momentum measure)

The single most rigorous momentum *feature* in this file and the cross-sectional ranking metric at the heart of Clenow's equities momentum system (Clenow, *Stocks on the Move*, Ch. 7). It replaces raw rate-of-change with a slope that is (a) comparable across price levels and (b) quality-weighted by trend straightness — directly addressing the "oscillators cluster at extremes / ROC is scale-dependent" weaknesses above. It is fully objective and programmable (passes the Aronson gate, §1a).

**Construction (default 90 trading-day window):**
1. **Fit an *exponential* regression**, i.e. an ordinary least-squares line on the **natural log of price** vs. time: `slope = SLOPE(ln Pₜ, t)`. Fitting log price makes the slope a **percent/day** growth rate (not dollars/day), so it is **comparable across price levels** and across stocks.
2. **Annualize:** `annualized_slope = exp(slope)^250 − 1` (250 trading days/yr). *Example:* slope 0.0006 → ~0.06%/day → ≈16%/yr.
3. **Multiply by the regression R²** (`R² = RSQ(ln Pₜ, t)`, range 0–1) to penalize choppy/gappy moves and reward smooth, straight-line advances:
   **Adjusted slope (ranking score) = (exp(slope)^250 − 1) × R².**
   A stock that gaps up on a takeover and then goes flat earns a high raw slope but **low R²**, which pushes it far down the ranked list. Clenow's framing: *"volatility is the currency we use to buy performance."*

**Excel recipe (verbatim):** `LN(price)` column → `SLOPE()` of the log series against a time index → `EXP()` then `^250` to annualize → `RSQ()` for the fit quality → multiply `slope × R²`. Rank the universe descending and buy from the top.

**Two hard qualifier filters layered on the ranking (objective trend gates, Ch. 7):**
- **100-day MA trend qualifier:** a stock must be **above its 100-day moving average** to be buy-eligible — a failsafe against buying sideways/declining names when nothing is genuinely rising. (Note the asymmetry vs. the 200-day index filter below.)
- **Gap disqualifier:** **exclude any stock with a single move > 15% in the trailing 90 days** — the system wants orderly trends, not event-driven jumps (a second, harder cut on the same pathology the R² term penalizes softly).

**Index regime filter:** new buys are allowed **only when the S&P 500 is above its 200-day MA** (below = bearish = no new entries). Clenow stresses the specific indicator is **deliberately un-optimized** — *"it doesn't matter much"* — consistent with the §1a/§7 lesson that the edge is in the framework (broad ranking, risk-parity sizing, regime gate), not in any single parameter.

**Normalization / sizing tie-in:** position sizing is **ATR-based** so each holding contributes equal risk (volatility-parity), exactly as in Clenow's *Following the Trend* engine (§2) and Carver's vol-scaled forecasts (§3b, §4) — cross-ref **file 07** (ATR sizing) and **file 08** (universe ranking). This is the practical contrast to the *time-series* trend filters above: the adjusted slope is a **cross-sectional, rankable** momentum score for choosing *which* of many equities/ETFs to hold, whereas EWMAC/MA filters decide *whether* to hold a given instrument.

### 3b. Carver's continuous trend forecast — EWMAC ladder, forecast scaling & combination (Advanced Futures)

Carver's *Advanced Futures Trading Strategies* develops the EWMAC trend signal (§2) from a binary on/off switch into a **continuous, capped, risk-scaled forecast** — the objective successor to the discretionary MA cross, used as a *graded* feature rather than a flip (Carver, *Advanced Futures*, p.151–223). EWMA beats simple MAC (smoother, no day-drop-out noise; advantage biggest for fast filters, p.151–154). For span N, **λ = 2/(N+1)**; Carver fixes the **fast:slow span ratio at 1:4**, shorthand **EWMACₙ = EWMAC(n, 4n)** (ratios 2–6 are statistically indistinguishable) (p.193, 204).

- **Ladder of six speeds:** EWMAC **(2,8), (4,16), (8,32), (16,64), (32,128), (64,256)**. (1,4) is too noisy; slower than (64,256) correlates too tightly with buy-and-hold; adjacent filters correlate **~0.87**, 2-apart ~0.64 — diversification across speeds is real but modest (p.204–205). EWMAC(16,64) is "the star of the book" (p.200).
- **Trend strength → forecast (Strategy 7):** **Raw forecast = (fast EWMA − slow EWMA) ÷ σ_P** (crossover divided by *daily price* volatility — the same recent-vol estimate as §4). **Scaled forecast = raw × forecast scalar**, the scalar chosen (pooled across instruments) so **average absolute forecast = 10**; then **cap at ±20** (never more than 2× the average position) (p.181–186).
- **Forecast scalars by speed** (one per filter; consecutive values differ by ≈√2): EWMAC2 = 12.1, EWMAC4 = 8.53, EWMAC8 = 5.95, EWMAC16 = 4.10, EWMAC32 = 2.79, EWMAC64 = 1.91 (table 29, p.206).
- **Position from a forecast:** N = (forecast ÷ 10) × (Capital × IDM × weight × τ) ÷ (Multiplier × Price × FX × σ%) — the vol-target position scaled by forecast/10 (position ends ∝ 1/σ%², the mean-variance result) — cross-ref **file 07**.
- **Buffering to cut turnover:** band **B = 0.10 × (average long position)** around the unrounded optimal N; trade only to the **nearest band edge** when the current rounded position falls outside [N−B, N+B], else do nothing. Cuts turnover substantially with no performance loss (kills *linear* costs; not non-linear impact) (p.194–196).
- **Combining speeds (Strategy 9):** take a **weighted average of the *capped* forecasts** (cap-then-average, so no fast filter dominates a day) with forecast weights summing to 1. First drop filters too expensive for the instrument (turnover-vs-cost speed limit ≈0.15 SR; per-filter turnover EWMAC2 98.5 … EWMAC64 5.2, table 35), then weight survivors **equally** (avoid over-fitting the single best). Because the combined forecast's avg-abs falls below 10 (≈7.5 for all six), multiply by a **Forecast Diversification Multiplier (FDM)** then re-cap at ±20: 6 rules → 1.26, 5 → 1.19, 4 → 1.13, 3 → 1.08, 2 → 1.03, 1 → 1.00 (table 36, p.218–223). Small FDMs confirm trend filters are mutually correlated.
- **Trend rule = exit rule:** Strategy 6 holds +N in an uptrend and −N in a downtrend, flipping on the slow-EWMAC(64,256) crossover — "use the same rule to open and close" rather than a separate stop (a properly calibrated vol-scaled stop is a near-equivalent alternative) (p.166–169) — cross-ref **file 07** and the early-loss-taker result in §7.

---

## 4. Volatility & bands

A band slows trading and improves reliability without changing the trend profile; wider band = fewer signals, delayed entries, smaller average profit, more per-trade risk (Kaufman p.608). **Always use yesterday's trend calc with today's price** to avoid look-ahead (Kaufman p.612).

| Name | Formula | Typical params | Use |
|---|---|---|---|
| True Range / ATR | TR = max(H−L, \|H−Cₚᵣₑᵥ\|, \|Cₚᵣₑᵥ−L\|); ATR = MA of TR | 14, 20 | Volatility-aware sizing/stops; standardize per-stock for ML (Kaufman p.261; Jansen p.322) |
| Volatility band | MA ± s·(ATR or stdev) | s≈2, 20-day | Std-dev band most sensitive (closest), %-band smoothest. Separate wide-entry / narrow-exit bands (Kaufman p.612) |
| Bollinger Bands | 20-day MA ± 2σ of price | 20, 2σ (Leshik prefers 1.65σ for more signals) | 2σ ≈ 87% (prices not normal); **squeeze** = bands compress to ~50% of average → trade breakout; Bollinger's own use is **mean-reverting** (Kaufman p.615–24; Jansen p.176; Leshik p.121) |
| Modified BB (McNicholl) | smoothed center α=0.15 (≈20-day), multiplier f≈2.5 | — | Corrects the post-vol "bulge" faster (Kaufman p.617) |
| Keltner channel | MA of *typical price* (avg H,L,C) ± MA of bar ranges (use true range) | 10-day | Better in noisy markets, worse in trendy (Grimes p.173; Kaufman p.610) |
| Percentage band | MA × (1 ± c) | — | Avoid on back-adjusted futures and fixed-$ bands (Kaufman p.610) |
| High/Low bands | Apply MA to highs and lows separately | — | Enter long on high crossing MA-of-highs (Kaufman p.608); dual H/L envelope (MAC) far beats close-based crossovers, which run only 30–45% accurate (Bernstein p.85–86) |
| Adaptive Price Zone (Leibfarth) | Double-smoothed EMA band: 5-day EMA of 5-day EMA of (H−L) | 5 | Mean reversion (Kaufman p.614) |
| Kase DevStop | 2-day ATR avg − {1.0, 2.2, 3.6}σ of that ATR (20-day) from close | 20 | Three scaled stop levels; reset on 5/21 cross (Kaufman p.1577) |

**Std-dev reference:** ±1σ=68%, ±2σ=95%, ±3σ=99.7%. For a *volatility* distribution use a sorted frequency distribution, NOT mean±σ (which gives negative thresholds) — e.g., SPY 20-day annualized vol: 10% chance >28.3%, 1% >56.8% (Kaufman p.1572–73). **Avoid the bulge** by lagging the std-dev window (e.g., t−25..t−5) so the current spike can penetrate (Kaufman p.1576). **GARCH(p,q):** σ²ₜ = ω + Σαᵢσ²ₜ₋ᵢ + Σβᵢr²ₜ₋ᵢ, pick (p,q) by BIC; predicting the *sign* of next-day realized-vol change is ~60–67% out-of-sample but hard to monetize (Chan p.127–29). **"Free bars"** — bars entirely outside a band — signal an emotional/stretched extreme for fade or retracement entries (Grimes p.176).

**Z-score / Bollinger on a mean-reverting series as a feature (Chan, *Algorithmic Trading*).** For a series engineered to be stationary/mean-reverting — a cointegrating spread, a pair, or a de-trended price — the natural entry/exit indicator is the **z-score**: `z = (yₜ − mean) ÷ stdev` over a rolling lookback (the lookback often set to the **half-life of mean reversion** from an Ornstein-Uhlenbeck/ADF fit). Enter when `|z|` is large (e.g. ≥1–2), scale out / exit as `z → 0`; this is exactly a **Bollinger Band applied to the spread** rather than to raw price (bands at mean ± k·σ). Treated as a *feature* (a normalized distance-from-equilibrium), not chart lore — and only valid once the series passes a stationarity test (see §1b signature-plot / variogram gate, and **file 02** cointegration). Model **mid-prices, not trade prices**, or bid-ask bounce manufactures phantom reversion (Chan p.61).

**Recent-volatility estimate (Carver — the key technical input for sizing & EWMAC normalisation).** Default = **25-day simple MA of daily % returns**, or equivalently a **36-day EWMA** (A = 2/(1+36) ≈ 0.054), matching RiskMetrics' ~25-day-equivalent half-life. Look-backs from a few days to ~6 months barely differ pre-cost; **>20 weeks degrades** (Carver ch.10, App.D). This vol estimate is what makes EWMAC a *continuous, risk-scaled* forecast and what feeds ATR-style position sizing — cross-ref **file 07**.

---

## 5. Volume / flow indicators

| Name | Formula / definition | Notes |
|---|---|---|
| VWAP | Volume-weighted average price | Common short entry: price pushes quickly below VWAP, returns on low volume (Bellafiore p.289). VWAP-band(1.5) for pullback longs (DaveyAziz) |
| OBV / Volume Profile | POC (point of control), 70% value area, high-volume nodes | Descriptive context, not signals (LLMagents p.11–12) |
| TRIN / Arms | (advancing/declining stocks)/(up/down volume) | <1 bullish; real-time breadth/sentiment gauge (Leshik p.122–23) |
| Net order imbalance (MOC) | Exchange-disseminated buy/sell imbalance minutes before close | Institutional/ETF flow proxy; HFT arbs the print, retail can't — track the *trend* of imbalances (BrokerTest p.280). See **file 10** (microstructure) |
| Order-book imbalance / shape | Limit-order-book shape, turnover, open interest | Technical-sentiment inputs (Narang p.34–35). See **files 01 & 10** |

Volume/flow microstructure (order-book imbalance, queue position, MOC mechanics) is developed in **files 01 and 10**; this file points there rather than duplicating.

---

## 6. Price patterns & market structure (rule-form)

The **trendline is the single most important pattern**; longer-timeframe (weekly/monthly) trends are far more reliable than daily — use weekly for direction, daily/15-min for entry timing (Kaufman p.236, 327–29). Markets are sideways ~80% of the time, so **most breakouts are false** (Kaufman p.247). Discretionary chart patterns (head-and-shoulders, triangles) are the analog to data-mining; many quant funds that tried to systematize them failed because the patterns lack valid theory or aren't truly rule-based (Narang p.44, 151). Aronson classes hand-drawn trendlines, classical chart patterns, Elliott Wave, Gann and Magic-T as **subjective TA** — not falsifiable, "not even wrong" — and shows experts cannot tell real charts from random-walk charts, so a pattern's *visual* obviousness is no evidence at all (Aronson p.5, 38, 83). Anything in this section is usable only once reduced to an objective, backtestable rule (see §1a).

**Translatable rules:**
- **Support/Resistance & pivots:** pivot P = (H+L+C)/3; R = 2P − L, S = 2P − H; long above P (exit at R), short below P (exit at S) (151Strategies p.51; Kaufman p.1358). Alt: ±½·avg(H−L,14) around prior close.
- **Channel / breakout:** Donchian — B_up = max, B_down = min over T; bounce (buy floor/sell ceiling) or follow the breakout (151Strategies p.52).
- **Resistance-becomes-support:** after a breakout the stock should hold above prior resistance and ideally explode away; a retrace back to entry lowers win rate. **Failed breakout = large downside risk** (over-long crowd flushed) (Bellafiore p.130–31).
- **Failure tests / reversals (candles):** shooting-star = buyers failing (top); hammer = sellers failing (bottom); indecision candles (Doji, spinning top) inside a trend signal possible reversal — **never trade alone, require a confirmation candle** (first new 5-min high/low) plus S/R context (DaveyAziz p.50–53). **Key reversal day:** uptrend over n days AND today highest of n AND lower low AND lower close; filter to significant ones where today's TR > 1.5×20-day avg TR (Kaufman p.267–68). **Programmable candle:** Qstick = MA of body (close−open); body-momentum 14-day >70 whites dominate, <20 blacks (Kaufman p.323–25).
- **5-bar fractal pivot:** two lower-high bars each side = up fractal (mirror = down). SPY 2000–18 rule: buy when price breaks above a down-fractal high, stop at fractal low, take profit = fractal high-low range from entry — ~58% reliable (Kaufman p.1748–50).
- **Opening gaps (strong empirical result):** **downward gaps cross back above prior close ~98–100% of the time** (recovery bias); upward gaps cross below prior close 48–60%; markets tend to reverse the gap by close. Per-stock varies (AMZN bullish, GE no edge) (Kaufman p.1388–94).
- **Intraday structure:** opening bar is most volatile and decisive (holds ~25% of daily highs AND lows); volume U-shaped. S&P: by 12:30 NY, ~50% chance high already seen, ~61% low seen → a new high after 12:30 is bullish (Kaufman p.1379–80).
- **Market Profile (Steidlmayer):** frequency distribution of intraday price using TIME (30-min TPO letters). **Value area = 70% of TPO/volume range; point of control = most-traded price.** "Outside paper" (CTI3/4) is directional and moves the market when participation >30% as price leaves a sustained area; HFT adds volume but not price (Kaufman p.1616–20). See **file 10**.
- **Bulkowski rankings:** best bullish breakouts = rectangular-top, falling-wedge, ascending-triangle, double-bottom; **symmetric triangle is the most dependable** (works either direction) (Kaufman p.386–88).

Fibonacci/Elliott/Gann are covered skeptically: key Fib retracements 0.618 and complement 0.382 (0.382 is *not* itself a Fib ratio); EWO = MA(5) − MA(35) of (H+L)/2 (Kaufman p.1282–1300). Treat as secondary, backtest before use.

---

## 7. Practical guidance

- **Parameter / calc-period sensitivity is the most important decision** — bigger effect than the trend method itself. Popular periods: 3, 5 (week), 20–23 (month), 63 (quarter), 200 (stocks), 252 (year). Seasonal markets need trend ≤ 1 quarter (Kaufman p.624–26). Use the computer to *validate* an idea, not to discover one.
- **MA sequences / signal progression:** read trend direction across a ladder of calc periods (short→long). Orderly left-to-right progression = reliable; erratic alternation at the short end = untrustworthy; majority of up-vs-down trends = current trend (Kaufman p.677–81).
- **Redundancy / correlation among indicators:** RSI, Stochastic, Williams %R, CCI are largely the same bounded-momentum construct — they co-move and will give correlated features. Keep charts clean with few indicators (most lack edge per Grimes); flipping indicators/timeframes is a path to failure (Bellafiore p.45). For ML, decorrelate or regularize.
- **Look-ahead in indicator computation:** `rolling(n)` produces NaN for the first n−1 rows — `dropna()` before signal logic (Hilpisch p.89). Compute trend on prior bar, apply to today's price (Kaufman p.612). Model **mid-prices, not trade prices**, to avoid bid-ask bounce producing phantom (untradeable) mean reversion (Chan p.61).
- **Risk:reward decouples profit from indicator exits.** Fixed brackets (e.g., 2:1 = 1% stop / 2% target with limit orders) let you profit at <50% win rate without relying on indicator-based exits (DaveyAziz p.43). Indicators *indicate, they don't dictate* (DaveyAziz p.85). Corroborating evidence: Carver's "A vs B" exit experiment found an **early-loss-taker (stop-loss-style trend rule) beat an early-profit-taker in 27 of 31 futures** — cut losers, let winners run (Carver ch.1, App.B); cross-ref **file 07**.
- **Tooling:** TA-Lib implements 200+ indicators from price/volume, pandas/NumPy-compatible; compute per-ticker via `groupby().apply()` (Jansen p.194, 322–23).

---

## Cross-references
- **01 — Market Microstructure / Data:** order-book imbalance, mid-price vs trade-price, OHLCV feature plumbing.
- **02 — Time-Series & Statistical Models:** ARIMA/GARCH, cointegration z-scores (the Chan z-score/Bollinger-on-a-spread feature in §4 — half-life lookback, stationarity gate), CUSUM/GLR foundations for MA and filter rules.
- **07 — Risk & Position Sizing / Validation:** ATR-based stops and **volatility-parity sizing** (Carver 25-day/36-day-EWMA vol estimate and forecast→position formula §3b; Clenow ATR sizing behind the §3a adjusted-slope ranking), Kase DevStop, fixed-bracket R:R, early-loss-taker exits (the §3b "same rule opens and closes" trend-stop); **and the multiple-testing / data-mining-bias correction (deflated Sharpe, Bonferroni, holdout)** that Aronson's 6,402-rule null result and §1a/§1b demand before any indicator is trusted as a feature.
- **08 — Universe / Market Selection:** Commodity Selection Index, choosing instruments to apply trend vs mean-reversion; **cross-sectional momentum ranking** (Clenow's §3a exp.-regression-slope × R² adjusted slope used to rank and select the top equities/ETFs to hold).
- **10 — Execution & Intraday / Flow:** VWAP execution, MOC imbalance mechanics, Market Profile, HFT and order-book shape.

## To validate empirically
- **Edge decay:** re-estimate any indicator rule on rolling out-of-sample windows; published MA-crossover and pattern edges erode as markets mature (Harris p.231) and SMA crossover is known ineffective standalone on indices (Halls-Moore p.466).
- **Parameter robustness:** test indicator parameters on a *grid* (e.g., RSI 2/4/14, MA periods 3–252) and prefer plateaus over single peaks; calc period matters more than method (Kaufman p.624–26).
- **Multiple-testing / overfitting:** scanning hundreds of indicator/parameter combos inflates false positives (Harris p.231); apply deflated Sharpe / Bonferroni-style correction and reserve a holdout. **Benchmark of record:** Aronson's **6,402 objective TA rules on the S&P 500 showed NO statistically significant edge after data-mining-bias correction** (Aronson) — assume the same null until your rule beats it under correction; a profitable backtest is necessary, never sufficient (Aronson p.6), so demand a *theory* (e.g. behavioral under-reaction / risk-transfer premium) plus out-of-sample survival. Cross-ref **file 07**.
- **Objectivity gate (Aronson §1a):** before testing, confirm the signal is fully programmable into unambiguous positions; if it needs analyst interpretation (hand-drawn lines, Elliott/Gann, "obvious" patterns) it is subjective, unfalsifiable, and out of scope — code it or drop it.
- **Regime before rule (Tsay/TQP §1b):** compute the **volatility-signature plot / variogram** on the instrument to confirm whether any trend (rising) or mean-reversion (falling) actually exists at your horizon before deploying a trend or reversion indicator — most series are near-flat (near-random-walk).
- **Source rigor:** down-weight indicator definitions from low-rigor sources (LightScalp / Heikin Ashi Trader / SmartMoney) — encode the *standard* formula (Heikin-Ashi, 13/8/5 Alligator, two-sided Gator) and ignore the books' internally inconsistent variants (e.g. Gator `(Jaw−Teeth)+(Teeth−Lips)` at 13/21/55, plain-SMA-on-close Alligator).
- **Redundancy:** measure pairwise correlation among bounded oscillators (RSI/Stoch/%R/CCI) before stacking them as ML features.
- **Look-ahead audit:** confirm every indicator uses only data through t−1 for the signal applied at t, and that `dropna()`/warm-up periods don't leak future bars.
- **Mean-reversion realism:** verify any oscillator/band reversion edge survives on mid-prices and after costs — bid-ask bounce manufactures phantom reversion (Chan p.61). For a **z-score/Bollinger-on-a-spread** signal (§4), first confirm the series is actually stationary (ADF/half-life) and set the lookback to the fitted half-life rather than a round number.
- **Cross-sectional momentum (Clenow §3a):** test the **adjusted-slope (exp-regression slope × R²)** ranking against simpler benchmarks (raw 90-/126-day ROC, slope without the R² term) to confirm the R² penalty and the exponential/log fit add out-of-sample value; vary the regression window (e.g. 60/90/125 days) and prefer a plateau. Re-confirm the **100-day MA buy-gate, the >15% gap disqualifier, and the 200-day index regime filter** are not individually optimized (Clenow stresses they "don't matter much" — treat sensitivity to them as a red flag), and that the whole edge survives ATR-parity sizing and costs after periodic re-ranking/rebalancing.
