# 09 — Execution & Transaction Costs
*Trading System Knowledge Base · theme T09 · equities/ETF-weighted*

*Updated: includes Kissell (I-Star), Bouchaud et al. (square-root law), Grinold-Kahn, Aldridge, Hull.*

**What this covers:** Why execution quality determines whether a strategy survives contact with the market; a taxonomy of transaction costs and how to *measure* them (effective/realized spread, implementation shortfall, VWAP); the major execution algorithms (TWAP, VWAP, POV, Implementation Shortfall, close, liquidity-seeking) and a decision framework for choosing among them; the efficient-trading-frontier framing of optimal execution; the trader's-dilemma multi-period cost-aware optimization; order-placement tactics (limit vs. market, pegging, iceberg, SOR, dark pools); market-impact models (the Kissell-Glantz I-Star model and pre-trade cost estimation; the empirical square-root law and Bouchaud's transient/propagator model; Almgren-Chriss; Kyle λ; Roll/Glosten-Harris/Huang-Stoll spread decompositions); the turnover ⇄ value-added frontier and the value of rebalancing (Grinold-Kahn); a brief on market-making quotes (Avellaneda-Stoikov); HFT execution realities (what genuinely needs co-location); and concrete cost assumptions to bake into an equities/ETF backtest.

**Why it matters:** Costs erode alpha continuously and silently. A positive-expectancy system can still lose to the "vig" — commissions, fees, financing, spread, slippage, and your own market impact (Grimes, p.21). Most retail traders *underestimate* these costs, and the largest components (impact, opportunity cost) are precisely the hidden, hardest-to-model ones (Harris, p.420). The average active US equity manager underperforms the S&P 500 by 1–2%/yr, and that gap is attributable to costs (Treynor, via Grinold & Kahn, p.445); a top-quartile IR=0.5 manager can lose roughly *half* her gross return to costs (Grinold & Kahn, p.445). Costs disproportionately kill fast, high-Sharpe, small-per-trade strategies — exactly the ones that look best on paper.

**Primary sources:** Harris, *Trading and Exchanges* (pp.71–550); Johnson, *Algorithmic Trading & DMA*; Guo/Lai/Shek/Wong, *Quantitative Trading* (Almgren-Chriss, Avellaneda-Stoikov); Leshik & Cralle; Kaufman; Chan (*Quantitative Trading*, *Machine Trading*, *Algorithmic Trading*); Narang; Hilpisch; Kakushadze (151 Strategies); **Kissell, *The Science of Algorithmic Trading and Portfolio Management* (the I-Star / Kissell-Glantz market-impact model)**; **Bouchaud, Bonart, Donier & Gould, *Trades, Quotes and Prices* (the square-root law and the propagator/transient-impact model)**; **Grinold & Kahn, *Active Portfolio Management* (turnover ⇄ value-added frontier, inventory-risk impact model)**; **Aldridge, *High-Frequency Trading*** (HFT cost taxonomy and execution realities); **Hull, *Options, Futures, and Other Derivatives*** (bid-ask/transaction-cost framing); **Carver, *Systematic Trading*** (standardised cost, the "speed limit"); Hasbrouck, *Empirical Market Microstructure* (Roll/generalized-Roll, Kyle λ, spread-component models); Chincarini & Kim, *Quantitative Equity Portfolio Management* (cost modeling inside the optimizer, rebalancing toward targets); Jurczenko (Bayesian-network cost model for crowded trades); plus *Quantitative Asset Management* and *Quantitative Portfolio Optimization*.

---

## 1. Why execution matters

Execution is not a cost center bolted onto a strategy — for many strategies it *is* the strategy's margin of survival. Several sources converge on this:

- **More trades is rarely better.** Each trade adds slippage + commission, usually reducing net profit. Larger bars (≥720-min/daily) survive costs; sub-10-minute breakouts are mostly false signals that bleed costs (Davey, p.34–42). Trade *selectively*, not "always-in."
- **The fair-coin trap.** Uninformed traders lose to informed traders whether they use limit OR market orders — they lose simply *because they trade*. A limit order fills you exactly when an informed trader wants the other side (you regret trading); a market order pays a spread that dealers widened to recoup informed-trader losses (the adverse-selection fee). The mitigation is the same everywhere: **minimize trading** (Harris, p.303).
- **Cost-sensitivity is concentrated.** Short-term, fast, directional/breakout systems carry the largest slippage (buying new highs, selling new lows) and the smallest per-trade profit, so they are the most fragile (Kaufman, p.118; SuccessfulAlgo, p.19). Mean-reversion entries have near-zero entry slippage (trading *against* the move) but pay full directional slippage when cutting a loser (Kaufman, p.1462).
- **Cost estimation is two-sided.** *Overstating* costs is as damaging as understating: inflated assumptions turn a good system into a paper loss and make you wrongly reject it (Kaufman, p.118).
- **Costs make construction a two-dimensional trade-off.** Without costs you trade off alpha against risk; *with* costs you simultaneously trade alpha against risk *and* alpha against cost, which forces precise alpha scaling — too-aggressive alphas just churn the book (Grinold & Kahn, p.387).

**The "speed limit" (Carver).** A blunt but powerful budgeting rule: never pay more than **1/3 of expected Sharpe ratio** in costs (Carver, ch.12). With a realistic max single-instrument SR of ~0.4, fully-systematic traders cap costs at **0.13 SR/yr**; asset allocators and semi-automatic traders (SR ~0.25) cap at **0.08 SR/yr**. Maximum sustainable turnover = cost-cap ÷ standardised cost (Section 2.3) — e.g. Euro Stoxx at 0.002 standardised cost permits ~65 round trips/yr (≈1-week holding), index spread bets at 0.01 only ~13. This is why **day trading (≥500 round trips/yr) is essentially impossible** even in cheap futures unless you can *capture* the spread (run near-zero or negative execution cost), and why most day traders lose.

**Pre-trade vs. post-trade TCA.** *Pre-trade* analysis forecasts cost (to choose an algo, order size, and urgency) — this is the natural home of the Kissell I-Star and square-root models in Section 6; *post-trade* TCA measures realized cost against a benchmark to audit execution quality and recalibrate assumptions. Performance monitoring is part of the system — compare live slippage to expectation; it often forces rule or position-size changes (Kaufman, p.118).

**A useful four-model TCA paradigm** (QuantAssetMgmt, ch.15): (1) a **Market model** predicting cost from history (lookback-only — safe to run live); (2) an **Execution model** that turns the prediction into an order plan (live); (3) a **Broker model** — a perfect-foresight slippage simulator used in research that **must be stripped before going live** (it sees the future); and (4) an **Attribution model** for the post-mortem. Confusing the Broker model for the Market model is a classic look-ahead leak.

---

## 2. Transaction-cost taxonomy & measurement

### 2.1 The components

Total cost = **explicit + implicit + opportunity** (Harris, p.420; Grinold & Kahn, p.446; Aldridge, ch.5):

| Component | Sub-items | Notes |
|---|---|---|
| **Explicit / transparent** | commissions, exchange/regulatory fees, taxes, desk costs | Fixed, easy to model, known ahead. ~cents/share equities, ~$1/contract futures (ChineseQuant, p.62). The *smallest and easiest* component (Grinold & Kahn, p.446). HFT pays the full short-term tax rate (Aldridge, ch.5). |
| **Implicit / latent** | bid-ask **spread** + **market impact** (+ slippage/latency, timing/price-appreciation risk) | Spread ≈ the cost of trading *one* share (Grinold & Kahn, p.447); ≈1 tick for liquid US stocks. **Impact** is the cost of the *additional* shares — "financial Heisenberg," every trade moves the market (Grinold & Kahn, p.447). It is the hardest to model and is now the **dominant** cost: empirically ~0.39% of equity turnover vs ~0.09% commissions (Aldridge, ch.5). |
| **Opportunity (missed-trade)** | unfilled-size × adverse move | Can *dwarf* execution cost; the cost you never see on a fill report (Harris, p.421). Per Wagner it **often dominates** all other components (Grinold & Kahn, p.449). |

A common operational decomposition (Chan, QuantTrading, p.22): **commission + liquidity cost (half the bid-ask spread) + opportunity cost (unfilled limit orders) + market impact + slippage** (the delay between signal and fill; on average a cost). The sum of commission + spread + impact is often called **implementation shortfall** (ChineseQuant, p.62). Hull frames the same idea from the derivatives desk: the bid-ask spread is a real, recurring transaction cost that a hedger or arbitrageur must clear before any theoretical edge is realized — round-trip spread costs accumulate fast for any strategy that rebalances frequently (Hull).

**Direct vs. indirect, with the maker-taker wrinkle** (TQP, p.384–385, 322): direct costs (fees, taxes, SEC charges) run ~0.1–1 bp; indirect costs are the spread (a few bps, and *endogenous*) plus impact (dominant). Maker-taker fees are not free money — paying a taker fee ϖ and earning a maker rebate effectively shifts the round-trip spread to **s + 2ϖ**.

**Market impact: temporary vs. permanent.** The spread itself splits into two pieces (Harris, p.298), and impact does too (Aldridge, ch.5; TQP, p.232):
- **Transitory / transaction-cost / temporary component** — normal cost of doing business, inventory-risk premium, monopoly rent; an *overshoot* that decays (power-law in time) and causes a mean-reverting *bid/ask bounce* once you stop trading → **temporary impact**.
- **Permanent / adverse-selection component** — recoups from uninformed traders what dealers lose to informed ones; *linear in size*, impounds information, and causes a random-walk (non-reversing) price move → **permanent impact**. Empirically it is the **larger** share of the spread in most markets (Harris, p.303).

The **Glosten-Milgrom** result ties these together: the adverse-selection spread = V_buy − V_sell, where V_buy/V_sell are the asset value conditional on the next trade's side; after a buy arrives, *both* bid and ask rise by half the adverse-selection component (Harris, p.300). Adverse-selection cost rises with order size, which is *why* large orders have large impact and why dealers quote small orders that look like sliced large orders wider (Harris, p.290).

**Microstructure origin of impact** (Grinold & Kahn, p.447–448): the liquidity supplier charges for two distinct risks — (1) **adverse selection**, because larger/more urgent trades signal an informed counterparty; and (2) **inventory risk**, compensation for holding the position until an offsetting trade arrives. Both rise with trade size, so **market impact increases with volume**. This is the same α (adverse-selection) + β (inventory) split that the Huang-Stoll spread decomposition estimates econometrically (Section 6.5).

**Timing risk** — the variance of cost from price moving while you work the order — and **opportunity cost** are the two costs an aggressive schedule reduces and a slow schedule increases. This trade-off is the heart of optimal execution (Sections 4 and 6.4).

### 2.2 The measurement formulas

**Signed-difference cost** (the master formula; Harris, p.422):
```
Cost = TradeSize × TradeSign × (TradePrice − BenchmarkPrice)
TradeSign = +1 for a buy, −1 for a sell
```
Costs across both sides of a trade sum to zero — one side's cost is the other's profit. The benchmark choice is everything.

**Effective spread** (Harris, p.424):
```
Effective spread = 2 × TradeSign × (TradePrice − midpoint_at_time_of_trade)
```
The single liquidity premium is the signed difference itself (≈ half-spread for a small marketable order). It is the **least noisy** estimator and the best default for *small retail* orders, but it is useless for judging timing skill and **underestimates the cost of split orders** (later child trades have already moved the midpoint).

**Realized spread** (Harris, p.425):
```
Realized spread = 2 × TradeSign × (TradePrice − midpoint_post-trade)   (e.g. +5/10/15/60 min)
```
Realized < effective when the price continues in the aggressor's direction. Two useful identities (Harris, p.426):
```
Effective − Realized ≈ dealer's loss to informed traders (the permanent move)
Quoted − Effective   ≈ price improvement actually given
```

**Implementation shortfall** (Perold's "paper portfolio"; Harris, p.424; Grinold & Kahn, p.449; Treynor). Benchmark = the **decision-time midpoint** (fixed *before* the order has any impact, so it cannot be gamed):
```
IS = filled_size × (avg_trade_price − decision_midpoint)      [execution cost]
   + unfilled_size × (current_price − decision_price)         [opportunity cost]
```
IS is immune to split-order, momentum/contrarian, informed-trader, and gaming biases → **the best estimator when the data is available** (Harris, p.429; "the best measure of cost," Grinold & Kahn, p.449). It compares the actual portfolio against a frictionless paper portfolio executed instantly, so it captures spread, impact, *and* opportunity cost in one number — the three things VWAP-style measures individually miss. Plexus's "Iceberg" decomposition further splits IS into manager timing (decision→order-to-desk), trader timing (order-to-desk→release), market impact (release→execution), and missed-trade opportunity (decision→price 30 days later, unfilled part). Illustrative magnitudes: ~12 bps commission and 20 bps *visible* impact vs. **53 bps timing + 16 bps missed-trade hidden** — the hidden costs dominate, so measure *all* categories (Harris, p.436).

**A censored-data warning** (Grinold & Kahn, p.450–451): tick-by-tick records show executed trades but *not* the orders that were never placed or never filled, so they are **biased/censored**. Realized costs computed from fills therefore systematically **underestimate expected costs** — the trades you skipped because they looked too expensive are invisible. This is the empirical face of the opportunity-cost problem.

**VWAP benchmark** (Harris, p.425; Leshik, p.19):
```
VWAP = Σ(size · price) / Σ size
```
Easy and computed daily, but if you are most of the day's volume your measured cost → 0 despite paying full spread + impact; it is partially gameable by spreading fills to match the market VWAP (Harris, p.428). VWAP-based methods measure impact only *crudely*, **miss opportunity cost entirely**, and are gameable (Grinold & Kahn, p.450). Opening/closing-price benchmarks are the **noisiest** and most biased (momentum/contrarian/informed/gaming).

**Estimator trade-off** (Harris, p.427): accuracy wants a benchmark *close in time* to the trade; detecting timing skill wants one *far* from it — opposing goals, so average over many trades.

**Annualized-cost rule** (Grinold & Kahn, p.387): point-in-time costs must be amortized against the horizon over which alpha and risk accrue:
```
annualized TC = round-trip cost / holding period (in years)
```
A 2% round-trip cost on a 6-month holding is 4%/yr of drag; the same cost on a 2-year holding is only 1%/yr. This is what makes holding period (≈ 12/turnover months) the lever that decides whether a given edge survives.

**Econometric estimators when no quote data exists** (e.g. open-outcry futures; Harris, p.434; Hasbrouck) — see Section 6.5 for the full spread-decomposition family. The quick ones:
- *Average absolute price change* ≈ spread when quotes are constant.
- **Roll's serial-covariance estimator:** `Effective Spread = 2·√(−SCov)` of adjacent price changes (unbiased only with large samples, equal-probability buy/sell, and order arrival uncorrelated with quote changes — else it underestimates). Hasbrouck derives this cleanly: the negative first-order autocovariance of returns *is* the bid-ask bounce (Section 6.5).
- **Glosten-Harris order-flow regression:** `ΔP = A·Q·Size + a·ΔQ + b·Δ(Q·Size) + ε`, separating the permanent (adverse-selection, ∝ size) effect `A` from the transitory (a, b) effect.

**Marginal vs. average** (Harris, p.437): trade more aggressively only while *marginal* opportunity cost > *marginal* transaction cost; most traders (wrongly) proxy marginal with average.

### 2.3 Standardised (vol-adjusted) cost and turnover — Carver

To compare costs *across instruments* on a risk-adjusted basis, Carver normalizes by volatility (ch.12):
```
Standardised cost = (2 × C) / (16 × ICV)      [SR units lost per round trip]
```
where C = cash cost to trade one block (execution + fees + tax), ICV = daily instrument-currency volatility, and 16 ≈ √252 annualises. The key, counter-intuitive consequence: **lower-volatility instruments have *higher* standardised cost** — a further reason to avoid them in a cost-sensitive system. Cost types entering C: execution (≈ ½ spread for a small market order), per-ticket fee (£5–15 retail), per-contract/per-100-share fee, and %-of-value tax (UK stamp duty 0.5%).

**Typical standardised costs (Carver):** cheapest futures (FTSE/NASDAQ) ~0.001; an average future (WTI) ~0.0024; **index spread bets ~0.01**; individual-equity spread bets higher; **ETFs ~0.08** (worked example: a low-vol inflation-linked bond ETF). In short, **equities/ETFs are 10–80× costlier than futures on a risk-adjusted basis** — a sobering input for an equities/ETF system and a strong argument for longer holding periods there.

**Turnover** = round trips per year of an average (vol-scalar) position; **holding period = 12 / turnover months**. Sources of turnover, in descending order: forecast changes > price-vol changes > capital changes (~3%/day at a 50% vol target) > FX > system-parameter meddling (eliminate the last by *not* fiddling). **Practical tuning:** slow down the volatility-estimate look-back for expensive instruments (a longer MA cuts turnover), and reserve cheaper/faster signal variations for only the cheapest instruments — Carver's own costs vary ~40× across his futures, so he runs fast rules *only* on cheap markets (ch.12).

---

## 3. Execution algorithms

These "Tier-1" agency algorithms exist to *get the trade* anonymously, without market impact or being front-run; immediate per-trade P&L is secondary (Leshik, p.19). Each sits somewhere on the **impact-vs-timing-risk** curve: trade fast → low timing risk, high impact; trade slow → low impact, high timing risk. Aldridge (ch.15) frames the machinery as **three layers** that any institutional stack implements: a **macro trader** (decides slicing, timing, child size, horizon), a **micro trader** (limit vs. market, exact price), and a **smart router** (which venue).

| Algo | Mechanism | When to use | Key params | Trade-off position |
|---|---|---|---|---|
| **TWAP** | Splits the order *evenly* across equal time slices | Small/illiquid names where a volume profile is unreliable; when you want to credibly signal "uninformed" (time-slicing, Harris p.290) | duration, slice count, randomization | Predictable schedule → ignores volume; medium impact. Theoretically optimal under a *martingale* (no-signal) price with an exponential impact propagator (TQP, p.388) |
| **VWAP** | Slices proportional to expected market volume across the day ("waves"/volume smile) | The standard buy-side↔sell-side block benchmark; liquid names with a stable intraday profile | lookback window (key tunable), price/volume constraints | Tracks volume → lower impact than TWAP for liquid names |
| **POV / Participation** | Executes a fixed % of *live* volume to stay "under the radar" | When you want impact to scale with available liquidity and don't need a fixed completion time | participation rate (e.g. 10–20%) | Self-throttling; completion time is uncertain. **Caution:** a POV algo that ignores its *own* contribution to volume can spiral — this feedback helped cause the **2010 flash crash** (Aldridge, ch.15) |
| **Implementation Shortfall / Adaptive Shortfall** | Front-loads or rebalances the schedule to minimize cost vs. the *decision price* (impact + λ·timing-variance) | When the arrival price is the true benchmark and you can specify risk-aversion (urgency) | risk-aversion λ, urgency, price/volume limits | Directly optimizes the Section-4 frontier; "adaptive" reacts to realized price. Risk-aversion ⇒ front-loaded (Almgren-Chriss, Section 6.4) |
| **Market-on-close / close** | Concentrates fills at the closing auction | Index/ETF rebalances and benchmarks pegged to the close | target close %, limit guard | Minimizes tracking error to the close; auction-impact risk |
| **Liquidity-seeking / opportunistic** | Hunts resting liquidity (incl. dark) and accelerates when it appears, slows when it's thin | Large orders where you'd rather catch blocks than follow a clock | aggression, venue list, min-fill size | Opportunistic; low signaling if it pings dark pools |

**Schedule detectability — a real caution.** TWAP/VWAP/POV are optimal only in narrow conditions (a martingale or cleanly-trending price), and scheduled child-order streams are **detectable via autocorrelation and Fourier analysis even when randomized** (Aldridge, ch.15). TWAP in particular is vulnerable to sniffer/front-running algos because of its regular cadence — counter with **skipped waves, fuzzy spacing, fuzzy share counts, or an RNG** (Leshik, p.21), but understand that randomization only raises the bar, it does not make you invisible. VWAP's volume profile is also unreliable in thinly-traded names (Leshik, p.20).

**Minimal-impact / smart order routing** (Aldridge, ch.15): place **market orders where limit liquidity is deepest**, place **limit orders where it is thinnest**, and size each child order **≤ top-of-book** so its footprint is minimal. Advanced models target constant order-book **resilience/replenishment** — i.e. trade only as fast as the book refills. (A limit-order's own impact is empirically only ~25% of a comparable market order's — Aldridge, ch.5 — which is part of why passive child orders leak less.)

**Why time-slicing works (a deeper reason than just impact):** breaking a large order into timed small pieces credibly signals you are *not* demanding immediate execution → you look uninformed → you access more liquidity at better prices (Madoff "Time Slicing," Harris, p.290). This is also the strategic content of **Kyle's multiperiod model** (Hasbrouck, p.33): a strategic informed trader internalizes the adverse price concession of large size and therefore *optimally spreads trades over time* — order-splitting is not a heuristic, it falls out of the theory.

**Splitting/slicing** is standard for large orders; in discriminatory-pricing markets, hiding the full size yields better average fills (Harris, p.72). But splitting *adds* slippage even as it cuts impact, so it is usually unnecessary for retail-size orders (Chan, QuantTrading, p.88).

### 3.1 An algorithm-selection decision framework

Pulling the sources together (Kissell; Aldridge ch.15; Harris; TQP), a practical chooser for the macro-trader layer:

1. **Start from the benchmark you are graded against.** Arrival/decision price → Implementation Shortfall. The close → MOC/close. A VWAP mandate → VWAP. No external benchmark, just "minimize cost" → POV or liquidity-seeking.
2. **Estimate pre-trade cost and size relative to liquidity** (Section 6). Compute Q/ADV and the I-Star / square-root impact estimate. If Q/ADV is small (≪1%), almost any algo works and you should favor the cheapest, lowest-signaling one. If Q/ADV is large, impact dominates and the schedule choice matters a lot.
3. **Set urgency / risk-aversion λ from the alpha decay.** Fast-decaying signal (the edge evaporates intraday) → front-loaded / high-λ Implementation Shortfall. Slow or no decay → spread out (low-λ, TWAP/POV) to minimize impact. Formally, an expected drift sets the optimal horizon `T* ∝ √Q` and optimal size `Q* ∝ α` (TQP, p.392–393; see Section 6.4).
4. **Pick participation style by liquidity stability.** Stable intraday volume profile and liquid name → VWAP. Unstable/thin or you simply want impact to self-throttle → POV. Want to catch blocks → liquidity-seeking across dark venues.
5. **Choose order aggressiveness at the micro layer by the price-of-liquidity rule** (Section 5): take when the spread is narrow, post when it is wide; market orders where the book is deep, limit orders where it is thin.
6. **Randomize and cap footprint** (skip/fuzz waves, child size ≤ top-of-book) to blunt detection, accepting it is mitigation not invisibility.

---

## 4. The efficient trading frontier & choosing risk-aversion

Optimal execution trades **expected impact cost** against the **variance of cost (timing risk)**. The **Almgren-Chriss** framework formalizes this: choose the liquidation schedule that minimizes

```
minimize   E[cost] + λ · Var[cost]
```

where `E[cost]` is the (mostly impact) expected execution cost and `Var[cost]` is timing risk from price volatility over the trading horizon; **λ is the trader's risk-aversion** (ChineseQuant, Almgren-Chriss; Aldridge ch.15 writes the same object as `Cost(α) + λ·Risk(α)`). Sweeping λ traces out the **efficient trading frontier**: each point is the minimum-variance schedule for a given expected cost (or vice versa).

- **λ → 0 (risk-neutral):** trade slowly to minimize impact, accepting large timing risk → the schedule approaches even/TWAP-like trading.
- **λ large (risk-averse):** trade fast to cut variance, paying more impact → front-loaded execution.

Choosing the benchmark and λ is therefore an explicit business decision about urgency. The decision-price (implementation-shortfall) benchmark pairs naturally with this objective, since the variance term is measured against the arrival price. (Section 6.4 gives the closed-form Almgren-Chriss trajectory and the propagator-based generalization from Bouchaud et al.)

This connects to **multi-period / dynamic** portfolio choice more broadly. With transaction costs, the optimal policy develops a **no-trade region**: positions inside it are left alone; outside it, intensive ("singular control" / big-bang) trading pushes the position back to the boundary (Samuelson-Merton / Davis-Norman, ChineseQuant, p.65). The practical lesson for a rebalancer: define a no-trade band so you only pay costs when drift is large enough to justify them — but beware that long inactivity concentrates trades into rare, high-impact rebalances (diBartolomeo, ChineseQuant, p.64). See Section 8.x for the value-of-rebalancing frontier (Grinold-Kahn) and Section 5.x's "aim portfolio" / partial-adjustment result.

---

## 5. Order-placement tactics

**Limit vs. market — the core trade-off** (Harris, p.73; Grinold & Kahn, p.467): market orders carry *execution-price* uncertainty (you fill, but at what price?) and *move* the price; limit orders carry *fill* uncertainty (you control price, but may not fill) and hand the market a **free option** — and risk one-sided fills in a big move (you fill only on the side that goes against you). Quantify both when routing. Grinold & Kahn's prescription: **use limit orders sparingly — mainly on the highest-impact stocks, with limit prices set close to the market.**

- **Price-of-liquidity rule** (Harris, p.381): use **market orders when the spread is narrow** (taking is cheap) and **limit orders when the spread is wide** (offering is attractive) — valid only when you know nothing about value. A narrow spread created by a single aggressive limit order is one-sided.
- **Marketable limit orders** are the pragmatic default: a limit placed *across* the spread fills immediately like a market order but caps runaway slippage (Grimes, p.177). Plain market orders have no recourse on a bad fill.
- **Directional/breakout entries** are the highest-risk placement: thin, fast, crowded books mean slippage can erode the whole edge and realized loss can exceed intended risk (Grimes, p.27; Kaufman, p.118). Where possible enter *before* the breakout level to capture the move ("free exposure"); on a true breakaway gap, enter immediately at market — one big favorable move offsets many poor fills (Kaufman, p.254).
- **Cheap stocks need price discipline:** below ~$5, buy mostly on the bid — a $3 stock can move 30–40%, so the entry price dominates (PlayBook, p.133). Habitual aggression (always paying the offer / hitting the bid) is a sign of bad trading and raises costs; add liquidity when you can (PlayBook, p.76).
- **Limit-order pricing model** (Harris, p.382): trade execution probability against price; model fill probability from size resting at better prices, volatility, and trader interest.

**When does a passive/limit order actually pay? — the martingale-wash result (TQP, p.395–398).** With *no signal* and a martingale price, a buy limit order placed a distance `d` below the mid has expected slippage **`E[Δ](d) = 0`**: the saving when it fills exactly cancels the opportunity cost when the price runs away (optional-stopping theorem). So passivity is not free alpha. Two refinements with teeth:
- If your order is large enough to have impact, `E[Δ](d) = I_LO(d) > 0` — **limit orders cost their own impact** (just less than a market order's).
- With return autocorrelation ρ, `E[Δ](d, ρ) = φ_exec · d · ρ`. Therefore **trending markets are *detrimental* to passive/limit execution and to market-making; mean-reverting markets are *favourable*.** Match your order aggressiveness to the autocorrelation regime of the name.
- For **large-tick** assets, **queue position decides** limit-order profitability: high priority benefits from the bid–ask bounce; low priority suffers adverse selection from sweeping orders.

**Order-exposure / hiding tactics** — leaking size is the main *avoidable* execution cost (Harris, p.144):
- **Iceberg / reserve orders:** show only small (ideally randomized) child slices of a large order; a limit-order long-duration variant exists (Leshik, p.21; Harris, p.144).
- **Pegging:** randomized limit orders that trail the market (Leshik, p.21).
- **Split across brokers / use anonymity** to dodge front-runners; **market-not-held** gives the broker discretion (no accountability for missed fills) (Harris, p.145).

**Smart order routing (SOR) & venue selection:**
- SOR routes child orders across venues for liquidity, fee, and anonymity; routers "sweep the market," taking liquidity from all venues at once (Harris, p.534). **Reliability is load-bearing** — a dropped connection mid-trade risks double execution or an unhedged leg; use stop-loss orders as a dead-man switch when control may be lost (Harris, p.550).
- **Maker/taker economics:** ECNs pay a **maker rebate** funded by takers; in competitive equilibrium this just narrows the equilibrium spread (Harris, p.536) — equivalently, paying a taker fee ϖ shifts your effective round-trip spread to `s + 2ϖ` (TQP, p.322). Paying to *add* (inverted venues like BZX) buys head-of-queue and discourages rebate-seeking HFTs from front-running stat-arb (Narang, p.168). Limit orders in ECNs suffer **adverse selection**: at the NBBO they rarely fill (internalizers grab benign flow) but fill fast when prices move toward them → systematic regret (Harris, p.520).
- **Dark pools** (>40 for US stocks): execute at the **NBBO midprice** (save half the spread), use pro-rata not time priority, and generate **no order-flow signal** (avoiding front-running of your follow-on orders) (Narang, p.171). Risks: midprice latency-arb front-running, spoofing/midprice manipulation, and complicit pools leaking resting orders. Mitigation: use low-adverse-selection pools (e.g. IEX-style delay) plus **IOC**, and *measure* adverse selection = P&L(unfilled) − P&L(filled) over 1s–30min (Narang, p.174). "Black Lance"-style algos ping dark pools to find liquidity (Leshik, p.21).
- **Payment for order flow (PFOF) / internalization:** in competitive markets PFOF is competed away into lower commissions, so net cost (spread + commission) is roughly invariant to the best-execution standard — therefore **measure *net* cost (spread + fees + impact), not commissions alone** (Harris, p.516). Avoid PFOF routing for your own flow with DMA brokers (IB/Lime) (Narang, p.10). Watch your own flow's **toxicity**: "hot" flow (prices rise after your buys / fall after your sells) marks you as informed; dealers won't pay for it (Harris, p.519).

**Order-book data hierarchy** for cost modeling and execution (QuantAssetMgmt, ch.15): HLOC bars < BBO (best bid/offer) < ticks < imbalance bars < full limit-order book — each level adds information (and cost/latency) for predicting and minimizing impact.

---

## 6. Market-impact models

This is the analytical core of pre-trade cost estimation. There are two complementary modeling traditions — a **practitioner pre-trade model** (Kissell-Glantz I-Star) and an **empirical/academic law plus a dynamical model** (the square-root law and Bouchaud's propagator) — and they agree on the headline: **impact rises ≈ as the square root of size relative to liquidity, scaled by volatility.**

### 6.1 The Kissell-Glantz "I-Star" market-impact model (the practitioner pre-trade workhorse)

Kissell & Glantz model the *instantaneous* (theoretical) impact of executing an entire order of size Q, then split it into temporary and permanent pieces according to how fast you trade. The **I-Star** form is a power law in size-relative-to-liquidity scaled by volatility (Kissell):

```
I* = a1 · (Q / ADV)^a2 · σ^a3        [instantaneous impact, in bps]
```
- `Q/ADV` = order size as a fraction of average daily volume (the imbalance);
- `σ` = (annualized or daily) volatility of the name;
- `a1` = a scaling constant; `a2` ≈ the size exponent (≈ **½**, the square-root regime — see 6.3); `a3` ≈ the volatility sensitivity.
- The author's **fitted parameter values** (Kissell's published US-equity calibration) are on the order of **a1 ≈ 700, a2 ≈ 0.55, a3 ≈ 0.71** — i.e. impact is mildly *concave* in size (close to square-root) and slightly less-than-linear in volatility. These are starting points: they **must be re-estimated on your own fills** (Section "To validate").

**Temporary + permanent split via participation (POV).** The realized cost is not all of I*; it depends on *how aggressively* you trade. Kissell allocates I* between a permanent part (impounded regardless of speed) and a temporary part (the cost of demanding liquidity faster), driven by the **participation rate POV = Q / (Q + V_trade-interval)** (equivalently order size vs. the volume that trades alongside you):

```
Permanent impact  P*  = (1/2) · I*                       (roughly half of I*, info-driven)
Temporary impact  T*  = a4 · I* · (POV)^a5 / (1 − POV)   (rises steeply with participation)
Total cost (bps)  MI  = b1 · T* + (1 − b1) · P*
```
where `a4, a5, b1` are additional fitted constants (b1 ≈ 0.9 in Kissell's calibration). The intuition that drops out: **permanent impact is a function of total size; temporary impact is a function of trading *rate*** — trade the same Q slower (lower POV) and you cut the temporary component while the permanent component is unchanged. This is exactly the lever the execution algorithms in Section 3 pull.

**Pre-trade cost estimation** then proceeds: feed Q, ADV, σ, and a candidate strategy (which sets POV / horizon) into the equations to get an expected cost in bps *and* a cost-vs-urgency curve; sweep POV (or λ) to trace the **efficient trading frontier** of Section 4; pick the strategy whose expected cost and timing risk match the alpha's urgency. The Kissell model is the canonical engine behind "what will it cost to trade this, and which algo should I use?" Kissell-Glantz-style models all follow the same template — a fitted function of size/ADV, volatility, spread, and urgency that separates temporary from permanent impact (and is what Kaufman p.180, Harris p.438 gesture at).

### 6.2 The inventory-risk derivation (Grinold-Kahn) — where √(size) comes from

Grinold & Kahn (p.449–453) derive the square-root shape from first principles, which is useful for sanity-checking any fitted model:
```
T_clear  ≈ V_trade / V_daily                       (time for the dealer to clear inventory, Eq.16.1)
σ_inv    = σ · √(T_clear / 250)                     (inventory risk over that horizon, Eq.16.2)
impact   ≈ c · σ_inv                                (impact ∝ inventory risk, Eq.16.3)
Cost     = commission + spread/(2·price) + c_x·√(V_trade / V_daily)   (total, Eq.16.4)
```
Because `T_clear ∝ V_trade`, inventory risk ∝ √V_trade, so **market impact ∝ √(amount traded)** and *total* cost (price × shares × impact) ∝ (amount)^{3/2}. This matches the classic Loeb (1983) data. Their memorable rule of thumb: **it costs about one day's volatility to trade one day's volume.** (TQP, p.236 states the same constant differently — trading 1% of daily volume moves the price ≈ √1% = 10% of a daily σ.)

### 6.3 The empirical square-root law of metaorder impact (Bouchaud et al.) — the central empirical result

The single most robust empirical regularity in execution. Splitting a parent order (a **metaorder**) of total volume Q and sign ε into child orders, the average **peak impact** (price move from first to last fill) obeys (TQP, p.234):
```
I_peak(Q, T) ≈ Y · σ_T · (Q / V_T)^δ           for  Q ≪ V_T
```
- `σ_T` = volatility over the execution horizon T; `V_T` = total market volume over T;
- `Y ≈ 0.5` for US stocks (an O(1) constant);
- `δ ≈ 0.4–0.7`, empirically **≈ 1/2** ("square-root").

**It is astonishingly universal:** the same law holds across equities, futures, FX, options, and Bitcoin; before and after HFT; for large- and small-tick names; and for both informed and uninformed flow. Exponent by market: δ ≈ 0.6 (US/international stocks), ≈ 0.5 (Bitcoin), ≈ 0.4 (volatility markets) (TQP, p.234–235).

**Why this is load-bearing for a trading system** (TQP, p.236–237):
1. **Impact is *not additive*.** The second half of a metaorder moves the price far less than the first half — there is a liquidity *memory time* `Tm`. You cannot just add up child-order impacts.
2. **Size enters as a fraction of *traded volume* V_T, not market cap M** (with M ≈ 200·V_T/day). This demolishes the old "1% of market cap → 1% price move" lore: trading **1% of daily volume moves the price ≈ √1% = 10% of a daily σ** — much larger than the cap-based intuition.
3. **Horizon T drops out.** Substituting `σ_T = √T·σ1` and `V_T = T·V1` gives
   ```
   I_peak ≈ Y · σ1 · √(Q / V1)
   ```
   which depends only on **Q, not on how fast you trade.** Economically, the price must adapt to the change in net supply/demand εQ regardless of execution speed — a deep and slightly unsettling result, because it means you cannot escape *peak* impact merely by going slow (though you can still cut *temporary* impact and *timing risk*; cf. Kissell's POV split, and the cost integral below).

**Domain of validity** (TQP, p.237–238): the square-root law holds for *intermediate* sizes and horizons — `τ_liq ≪ T ≪ Tm` and `V_best/V_T ≪ Q/V_T ≲ 0.1`, where `τ_liq` is the LOB refill time (seconds–minutes) and `Tm` the latent-liquidity memory (~days). Outside this band:
- **Very long T (≫ Tm):** impact becomes **linear** in Q (the permanent component dominates).
- **Very fast T (≲ τ_liq):** impact becomes **convex** — you eat straight through the visible book (this convexity is the microstructural rationale for circuit breakers).
- **Tiny Q (< V_best):** recovers linear.

### 6.4 Impact decay, the propagator/transient model, and optimal scheduling (Bouchaud)

The square-root law is a statement about *peak* impact; the full *path* matters for cost. After the last child fill, the price **reverts sharply, then slowly** (TQP, p.232, 359):
```
I_path(Q, t) = I_trans(Q, t) + I_∞(Q)
```
with `I_trans → 0` (the temporary part) and `I_∞` the permanent part. `I_∞` mixes a genuine *prediction/information* component (smart agents) and a purely *mechanical* reaction (even zero-intelligence flow leaves residual impact, as in the Santa Fe model — TQP, p.240). The decay time scales with the execution duration T itself ("the longer you push, the longer it takes to come back") — a manifestation of long-range **resilience**.

**The transient-impact (propagator) model.** Bouchaud's framework writes price as a convolution of past trades with a decaying kernel — equivalently (Gatheral 2010 general form, QuantPortfolioOpt p.85):
```
S_t = S_0 + ∫ f(x_s) · G(t − s) ds + noise
```
with `f` the instantaneous (per-trade) impact function and `G` the **propagator/decay kernel**. A **no-dynamic-arbitrage** principle constrains the pair: a power-law decay `G(t) = t^{−γ}` with `f(v) ∝ v^δ` requires **γ + δ ≥ 1** (else you could make money trading against your own impact). This is the dynamical model that *generates* the square-root law and the √-shaped intra-order path.

**The √-shaped slippage cost.** Because the impact path of the first φ-fraction of the order also obeys square-root, `I_path(φQ) ≈ √φ · I_peak(Q)`. Integrating gives the volume-weighted slippage (TQP, p.241):
```
C(Q) ≈ (2/3) · Q · I_peak(Q)            ⇒  cost per share = (2/3) × peak impact
```
(versus ½ × peak if impact were *linear*). The practical **unitary impact-cost estimate** is therefore:
```
unit cost ≈ (2/3) · σ_T · √(Q / V_T)
```
Worked number: trading **1% of daily volume on a 2%-vol stock ≈ 15 bps** (TQP, p.385) — an order of magnitude above spread/fee costs (~1 bp), confirming that **impact is the dominant cost for moderate-to-large orders.**

**Optimal scheduling with the linear propagator** (TQP, p.387–390). Minimize the quadratic impact cost over a schedule j(t) with `∫ j = Q`:
```
E[Δ] = (1/2) ∫∫ j(t) · G(|t − t'|) · j(t') dt dt' + Q·s/2
FOC:  ∫₀ᵀ G(|t − t'|) · j(t') dt' = ζ   (constant in t)
```
Solutions depend on the kernel:
- **Exponential propagator** `G = G0·e^{−ωt}` → a **"bucket" schedule**: a fraction `1/(2 + ωT)` is traded at the open and at the close, constant in between; it → **TWAP** as ωT → ∞.
- **Power-law propagator** → a **U-shaped** (front- *and* back-loaded) profile.
- The general optimum is **symmetric about T/2**, and `G` must be *absolutely monotonic* so the schedule never flips sign (no self-arbitrage).

**Almgren-Chriss as the risk-averse special case** (TQP, p.390–391). Add an inventory-risk penalty `Γ·σ²·∫(Q − q(t))² dt` for unexecuted shares; the optimal *remaining-inventory* trajectory is
```
q*(t) = Q · [1 − sinh(Ω(T − t)) / sinh(ΩT)],     Ω² = Γσ² / Ḡ0
```
Risk aversion ⇒ **front-loaded** execution (trade fast early to cut exposure); `Γ → 0` recovers TWAP. This is the same `E[cost] + λ·Var[cost]` frontier of Section 4, now with an explicit trajectory.

**Trading *with* a signal — this sets horizon and capacity** (TQP, p.392–393). If the trader expects drift `α(1 − e^{−t/Tα})`, the optimal horizon and size are
```
T* = √(Tα · Ḡ0 · Q / α)   ∝ √Q
Q* = 4·α·Tα / Ḡ0           ∝ α   (signal strength; as in Kyle)
```
So **stronger signals justify larger orders, and larger orders justify longer horizons** — the link from alpha to execution schedule. (This is the Gabaix-style alternative *explanation* of the √-law — informed traders schedule ∝√Q — but it wrongly predicts a *linear* intra-order path, contradicting the empirical √-shaped path, so the propagator mechanism is the better description; TQP, p.241–242, 393.) In the large-trading-rate limit with a non-linear propagator, the shortfall becomes essentially *independent of the schedule* (TQP, p.394) — a reassuring robustness result.

### 6.5 Kyle's λ and the spread-decomposition family (Hasbrouck)

The academic microstructure models give you econometric handles on impact and the spread when you lack a clean pre-trade calibration (Hasbrouck; QuantPortfolioOpt p.84):

- **Kyle (1985):** linear, permanent impact. `S̃_t = S_t + λ·Δθ`, where `Δθ` is signed order flow and **`1/λ` = market depth**. Multivariate version: λ is a positive-definite matrix acting on the trade vector. **λ — the price impact of order flow — is the central execution-cost parameter:** the coefficient mapping signed order flow to permanent price change, i.e. the price a trader pays for demanding liquidity / revealing information.
- **Roll (1984) implied spread from autocovariance** (Hasbrouck, p.13–14). With `Δp_t = −c·q_{t−1} + c·q_t + u_t`, the return autocovariances are `γ0 = Var(Δp_t) = 2c² + σ_u²`, `γ1 = Cov(Δp_t, Δp_{t−1}) = −c²`, and all higher ones zero. Hence
  ```
  c = √(−γ1),    σ_u² = γ0 + 2γ1,    spread = 2c
  ```
  **The negative first-order autocovariance of returns *is* the bid-ask bounce.** (Empirically the Roll spread often *understates* the quoted spread; the effective spread sits closer.)
- **Generalized Roll (adds adverse selection)** (Hasbrouck, p.44–45): the trade now permanently moves the efficient price, `m_t = m_{t−1} + w_t` with `w_t = λ·q_t + u_t`, and `p_t = m_t + c·q_t`. Half-spread = `c + λ` (fixed cost + adverse selection), giving `γ1 = −c(c + λ)`. This cleanly separates the *transitory* `c` from the *information* `λ`.
- **Huang-Stoll (1997)** (Hasbrouck, p.105): `ΔP_t = (S/2)·ΔQ_t + λ·(S/2)·Q_{t−1} + e_t` with **`λ = α + β`** = adverse-selection share α + inventory share β (identified only as a sum unless trade autocorrelation is modeled — which is the Grinold-Kahn α/β decomposition of Section 2.1).
- **Glosten-Harris (1988)** (Hasbrouck, p.103): adverse-selection `Z_t = z0 + z1·V_t` and transitory `C_t = c0 + c1·V_t` both scale with trade size `V_t`; estimable **from prices + volume *without* quotes** via state-space/MCMC filtering — useful for markets with no quote feed.
- **MRR (1997)** (Hasbrouck, p.104): efficient-price update `= θ·(x_t − ρ·x_{t−1})` (the innovation in trade direction), with the trade price adding `φ·x_t`; GMM-estimated.

### 6.6 Practitioner cost forms and estimation

**Almgren-style linear cost model** used inside portfolio optimization (151 Strategies, Appendix A, p.126) avoids full iterative cost optimization by charging a per-dollar cost and shrinking each expected return:
```
E_eff_i = sign(E_i) · max(|E_i| − τ_i, 0)        (effective return after cost)
τ_i = ζ · σ_i / A_i                               (per-dollar cost; A_i = ADDV)
```
normalized so the mean τ_i ≈ 10 bps. The structure (cost ∝ volatility / liquidity) is the same Almgren ingredient, and the same shape Carver's standardised cost captures.

**Ginter-Richie liquidity-cost form** (Kaufman, p.2000):
```
C = f(order size, volatility V, total volume Vt, equity/delivery volume) × K
```
with K larger when buying *into* a rising market. Two illiquidity regimes: fast (one-sided) markets and inactive (small-cap, deferred-futures, many ETF) markets — favor the fewest trades in the most-liquid instruments at equal gross profit.

**Empirical / regression estimation.** Where you have the data, estimate slippage by regressing realized slippage on volatility, volume, order size, time-of-day, and tick volume (solve `a0..a4`); then **volatility-adjust** slippage (more when vol is high) but cap a sensible minimum and stay conservative (Kaufman, p.1463). Aldridge (ch.5) gives the canonical impact-estimation recipe: an **event-study regression** of normalized post-trade return on trade size, adding spread, short-term volatility, and intertrade duration as covariates. Because **trade signs are strongly autocorrelated**, a **VAR** (Hasbrouck / Dufour-Engle) is needed to separate whether *size drives impact* or *impact drives subsequent trade direction* — otherwise the impact coefficient is contaminated.

**A Bayesian-network cost model for crowded trades** (Jurczenko, ch.11): a graphical model linking transaction cost ↔ stock characteristics (spread, turnover, volatility) ↔ meta-order side/size ↔ **net order-flow imbalance** (a *latent*, only-partially-observable "crowding" variable). Advantages over OLS/standard ML: it handles missing data and infers the latent imbalance's distribution via Bayes' rule. Findings worth carrying: **imbalance (not order size) dominates implementation shortfall** — you pay to trade *with* the crowd and get price improvement *against* it; a manager can update beliefs about market imbalance from their own order's side/size (sells are more informative); and cost-forecast accuracy is governed almost entirely by stock **volatility** (coef 0.78), with out-of-sample R² rising with order size. Complements the Kissell/Almgren square-root impact models rather than replacing them.

**Transaction-cost prediction features** to feed any such model (Harris, p.438): order size & price placement; contemporaneous spread width & displayed depth; recent volume, price momentum, and money-flow (uptick vs. downtick volume); market-wide average volume and volatility; and **market cap as a liquidity proxy** in equities (large caps are cheaper).

---

## 6A. Cost-aware portfolio optimization & the trader's dilemma

Execution cost is not just a per-trade number — it reshapes the *portfolio* you should hold and the *path* by which you get there. This section collects the optimization side.

### 6A.1 The trader's dilemma — trading is its own optimization (Grinold-Kahn, Kissell)

**Trading is a separate optimization from portfolio construction** (Grinold & Kahn, p.464–475). Once you know the target portfolio, you still must decide the *trajectory* of intermediate portfolios, maximizing
```
Utility = α_short − λ_short · ψ²_short − MI       (Eq. 16.12)
```
over the intermediate portfolios, where three forces pull in different directions:
- **Risk** pushes toward *fast* execution (get to the target so you track the immediate-execution benchmark);
- **Market impact** pushes toward *even spacing* (don't trade faster than liquidity refills);
- **Alpha** pushes the best trades *early* (or late, if the signal builds).

Modeling MI ∝ (trade rate)² and solving yields the clean dichotomy: a **market-impact-dominated** problem → **uniform (straight-line) trading** (≈ TWAP); a **risk-dominated** problem → **exponential approach to target**, `h(t) ≈ 1 − exp(−·)` (Eq. 16.15–16.16, 16A.22–26). This is the same trade-off Almgren-Chriss and the Bouchaud propagator solve in Section 6.4 — Kissell's **"trader's dilemma"** is exactly this multi-period, cost-aware optimization: balancing the cost of trading *too fast* (impact) against the cost of trading *too slow* (timing risk / alpha decay), made concrete by sweeping the participation rate in the I-Star temporary/permanent split.

### 6A.2 TC-aware mean-variance optimization & the no-trade region

The portfolio objective with costs (QuantPortfolioOpt, p.86; QEPM ch.10.5; QuantPortfolioOpt Prop 7.2):
```
max  wᵀR − (λ/2)·wᵀΣw − Γᵀ|Δw| − (1/2)·Δwᵀ Λ Δw
       │ gross alpha │  risk  │ linear/fixed │ quadratic / impact │
```
- **Linear (fixed/spread) costs** `Γᵀ|Δw|` create a **no-trade region**: when the current portfolio w₀ is inside it, *the optimal action is to not trade at all* (Prop 7.2, p.87). Linear impact → quadratic TC; power-law impact → nonlinear TC; **quadratic costs always make *some* trading optimal** (the no-trade region collapses to a point).

QEPM (ch.10.4–10.5) makes the practitioner version explicit: conventional cost = a fixed fraction `c` of traded value, `TC = c · TV` with `TV = Σ_i |V_t·w_i^a − V_t·w_i^b|`, and `c` can **vary per stock** (e.g. inversely proportional to ADV/liquidity) and depends on which names are bought vs. sold — so it is a function of `w^a`, not a constant, which makes the problem **non-linear/non-quadratic**. Their solution recipes:
- **Approximate (Appendix 10A):** first solve *ignoring* costs to learn the buy/sell **direction** of each name, fix `c` accordingly, then re-solve as a normal QP.
- **Exact (Appendix 10B)** and market-impact-model variants (Appendix 10C) also provided.

QuantAssetMgmt (ch.15) adds the pragmatic note that, because **estimation error eclipses model precision**, a **piecewise-linear cost term in the optimizer objective** is usually good enough — don't over-engineer the cost curve.

### 6A.3 Multi-period optimal trading: the "aim portfolio" (Garleanu-Pedersen)

For a *dynamic* program — maximize the present value of future excess returns penalized by risk and trading cost — **Garleanu-Pedersen** give a clean closed form (QuantPortfolioOpt, p.89): the optimal portfolio each period is a **weighted average of the current portfolio and an "aim portfolio"** (itself a blend of the current Markowitz portfolio and the *expected future* Markowitz portfolios). Operationally: **trade only partway toward the target each period.** Mei-DeMiguel-Nogales generalize to ℓp costs (p=1 linear, p=2 quadratic, 1<p<2 realistic market-impact); the **no-trade region is a parallelogram around the Markowitz portfolio that shrinks to it as the horizon → ∞**. G-P is *time-consistent*, whereas naive dynamic mean-variance suffers time-inconsistency. This is the dynamic-optimization cousin of the no-trade-band rebalancing in Section 4 and Section 8.x.

---

## 7. Market-making basics (brief)

For completeness, the mirror image of taking liquidity is *providing* it. **Avellaneda-Stoikov** gives optimal two-sided quotes for an inventory-averse market-maker (ChineseQuant): compute a **reservation price** that skews away from the mid as inventory grows (you quote to offload risk), then set a bid/ask **half-spread** that balances the rebate/spread captured against inventory risk and order-arrival intensity. The practical intuition appears throughout the trading sources: passive limit orders save the spread vs. aggressive orders, but the price of providing liquidity is **adverse selection** — passive fills cluster exactly when the market trades through you, i.e. against "toxic"/smart flow (151 Strategies, p.58; Narang, p.175). The TQP martingale-wash result (Section 5) is the quantitative version: with no signal `E[Δ](d) = 0`, and the maker only profits when the price is **mean-reverting** (ρ < 0) or when high queue priority lets it earn the bid-ask bounce before adverse selection sets in. A retail system rarely runs a true market-making book, but the same adverse-selection asymmetry governs whether your *passive* entry attempts help or hurt: in stocks/futures, adverse selection hits resting limit/passive orders (use limit-IOC or market-IOC to avoid resting) (Narang, p.175).

---

## 8. Practical guidance for a retail / small-fund equities system

**Cost assumptions to bake into backtests** (round-trip unless noted):

| Instrument | One-way assumption | Source |
|---|---|---|
| Liquid S&P 500 stock | ≈ 5 bps one-way (≈10 bps round trip) | Chan, QuantTrading, p.22 |
| Large-cap commission (one-way) | ≈ 2.4 bps; small-cap ≈ 5.9 bps | QEPM, ch.10.3 |
| Large-cap price impact (one-way) | ≈ 21 bps; small-cap total w/ delay ≈ 44.6 bps | QEPM, ch.10.3 |
| Liquid ETF (SPY-like) | similar to large-cap stock; check %-spread vs. range | Kaufman, p.1458 |
| ETF, risk-adjusted (standardised) | ≈ 0.08 SR/round-trip — ~10–80× a future | Carver, ch.12 |
| ES / index future | ≈ 1 bp one-way | Chan, QuantTrading, p.22 |
| Impact, moderate order (≈1% ADV, 2%-vol name) | ≈ 15 bps (≈ (2/3)·σ·√(Q/V)) | TQP, p.385 |
| Commission (IB retail) | min ~$1.30/order; $0.013/sh ≤500 sh else $0.008/sh | SuccessfulAlgo, p.19 |

**Modeling mechanics:**
- *Proportional cost (vectorized):* detect trades via `position.diff() != 0`, then subtract `tc` from the strategy return on those bars (Hilpisch, p.119).
- *Fixed costs need event-based backtesting:* apply per-order, e.g. `amount -= units·price·(1+ptc) + ftc` (Hilpisch, p.179). Vectorized fixed-cost handling is only an approximation (p.284).
- *FX/CFD cost is the spread, not commission:* `ptc = spread / mean_price`; trade signals off mid prices `(bid+ask)/2` (Hilpisch, p.232, 278). Hull's framing of the bid-ask spread as the relevant friction for derivatives hedging is the same idea.
- *Impact-aware backtests:* for orders that are a non-trivial fraction of ADV, charge the square-root impact `(2/3)·σ·√(Q/V)` *on top of* spread + commission, not just a flat per-share number — a flat number badly under-charges large orders and over-charges tiny ones.
- Express results as **$/contract or ¢/share** to verify commissions + slippage are actually covered (Kaufman, p.461).

**Rules of thumb for keeping costs small** (Chan, QuantTrading, p.87; Carver, ch.12):
- Avoid sub-$5 stocks (higher %-spread, more shares per dollar — see PlayBook, p.133).
- **Avoid low-volatility instruments** — they carry *higher* standardised (risk-adjusted) cost (Carver). Choose **high-volatility *and* high-volume** instruments so cost is a small % of the day's range (Kaufman, p.1457); the open-close range ≈ 50% of the high-low range (p.1459).
- Cap order size at ~**1% of average daily volume** (small-caps hit this fast) — and remember that 1% of volume already costs ≈ 10% of a daily σ in impact (TQP).
- **Respect the speed limit:** keep total cost ≤ 1/3 of expected SR; back out max turnover = cost-cap ÷ standardised cost (Carver). Day-trading turnover is unreachable unless you capture the spread.
- Scale capital across names by the **4th root of market cap**, not linearly, to preserve diversification (keep largest/smallest weight ratio ≤ ~10).
- Splitting large orders cuts impact but adds slippage — usually unnecessary for retail size.
- Slow the volatility look-back (longer MA) on expensive instruments to cut turnover; reserve fast signal variations for the cheapest names (Carver).

### 8.x The value of rebalancing & the turnover ⇄ value-added frontier (Grinold-Kahn)

Rebalancing is for **risk management, not alpha** — it is mechanically mean-reverting (it sells winners and so *sacrifices* momentum) (QuantAssetMgmt, ch.16). The question is how much turnover is worth paying for, and Grinold & Kahn give the cleanest answer (p.455–463):

- **The frontier `VA(TO)`** (value-added as a function of turnover; Grinold-Stuckelman) is increasing and concave, running from `VA_I` (the current/initial portfolio) up to `VA_Q` (the unconstrained optimal). Its **lower bound** (prorate a fraction TO/TO_Q of every trade) guarantees you **keep ≥ 75% of the incremental value added with only 50% of the turnover** (Eq. 16.10) — equivalently **≥ 87% of the IR at half turnover.** Half the trading buys you most of the benefit.
- **Beat the bound** two ways: (1) **schedule the best trades first** (largest alpha spreads), and (2) **exploit stock-specific cost differences** — in their example, distinguishing stocks by cost barely changed alpha/risk but **cut costs ~30%.**
- **Implied transaction cost** = the *slope* of the VA/turnover frontier at your chosen turnover; it reverse-engineers the cost assumption your turnover implies. Optimal turnover is where **`SLOPE(TO*) = TC`** (p.458–459). If the slope at your operating point (say 4.5%) far exceeds your believed round-trip cost (say 2%), reconcile by **raising the cost estimate, allowing more turnover, or scaling alphas down** (p.459–460).

**When does a trade clear the hurdle?** A parameter change (α, β, or premia) or a flow warrants trading **only if the expected-return gain exceeds the round-trip cost** — don't pay 5 bps to capture 3 bps (QEPM, ch.10.6). Match the **rebalance horizon to the model's periodicity**: monthly is the standard compromise (daily/weekly is too noisy, annual β's too unstable); *update* the estimates ≥ monthly but *rebalance* only when it pays.

**Rebalancing schemes** (QuantAssetMgmt ch.16; QEPM ch.10.6):
- **Calendar / benchmark / band / tolerance** rebalancing; a tighter *inner* tolerance band cuts churn; **volatility-adaptive bands** widen the no-trade region when vol is high. Compare turnover-vs-cost against a **continuously-rebalanced** benchmark, *not* buy-and-hold. **Dynamic risk targeting** generally beats fixed-allocation targeting (at the price of bigger trades).
- **Drift toward targets, don't snap to them**, to cut trading (and tax + impact) (QEPM ch.10.6):
  - *Standard:* `x_i = [w_i^target·(V_{t+1}+C_{t+1}) − w_i^before·V_{t+1}] / p_i`.
  - *Buy-only with a cash inflow (no selling):* allocate new cash only to *under-weight* names (faster convergence than pro-rata); if cash is insufficient, scale allocations down proportionally. Minimum cash to fully rebalance without selling = `V_{t+1}·max_i[(w_i^before/w_i^target) − 1]`. A symmetric sell-only algorithm handles net withdrawals.
  - **Equitize cash with index futures or sector ETFs** to absorb daily flows without trading the book; futures are preferred (more liquid, after-hours GLOBEX, partial long-term tax treatment) but need roll management beyond a few days.
- **"Flows are free rebalancing"** — route inflows/outflows to push the portfolio toward target so you pay no extra cost (QuantAssetMgmt ch.16).

**Tax-aware execution** (QuantAssetMgmt ch.16): lot selection (HIFO/FIFO/LIFO), wash-sale rules (30 days, across *all* household accounts), and estate step-up all interact with trading decisions. **Tax-loss harvesting** is a dynamic arbitrage whose benefit is *deferral + reinvestment* of the tax-alpha (~0.13%/yr in their example); it suffers **burnout** when cost basis gets too low, and a **long-only / no-leverage** mandate kills most of the benefit (a 130/30 structure helps).

**Broker / infrastructure** (Chan; SuccessfulAlgo): select on execution speed, dark-pool access, product range, and crucially an **API** plus a paper-trading account — not commission alone. DMA brokers (IB, Lime) avoid PFOF; latency/colocation only matters for genuine HFT (SuccessfulAlgo, p.26).

**What actually needs co-location / low latency (HFT realities).** Most strategies do **not** need it. Colocation, kernel-bypass networking, and microsecond-level optimization earn their keep only for genuinely latency-sensitive activity: (1) **passive market-making** that must update quotes and avoid being picked off when the NBBO moves; (2) **latency arbitrage** (e.g. exploiting the slow midpoint at a dark pool, or cross-venue price discrepancies); (3) **queue-position / maker-rebate** strategies on large-tick names where being first in the queue *is* the edge; and (4) any **scheduled child-order scheme that fears detection**, since adversaries running autocorrelation/Fourier analysis act fast (Aldridge, ch.5, ch.15). For a holding-period-of-days equities/ETF system, execution quality is dominated by *spread + impact + opportunity cost* (this file's Sections 2 and 6), not by microseconds — spend the effort on impact modeling and order-placement tactics, not on a colocated rack. (Aldridge's own taxonomy makes the same point: market impact ~0.39% of turnover dwarfs the latency-driven components for non-HFT flow.)

**Order-type default for a retail equities bot:** marketable limit orders to cap slippage; market orders acceptable for small (≤~1000-share) liquid orders where fill is near-certain and price moves little in the recalculation window (Leshik, p.45). Reserve true market orders for liquid names and use limit stops as guards. Match aggressiveness to the autocorrelation regime — be more willing to post passively in mean-reverting names, more willing to take in trending ones (TQP, Section 5).

---

## Cross-references
- **01 — Foundations / strategy taxonomy:** cost-sensitivity differs by strategy class (momentum vs. mean-reversion); fast strategies are the most cost-fragile; Carver's "speed limit" caps turnover at ~1/3 of expected SR, making day-trading edges nearly unreachable.
- **07 — Backtesting & validation:** proportional vs. event-based cost modeling, look-ahead/touch-fill pitfalls, conservative slippage assumptions; the QuantAssetMgmt "Broker model" (perfect-foresight slippage) is a look-ahead trap that must be stripped before live; impact-aware backtests should charge `(2/3)·σ·√(Q/V)` on large orders, not a flat per-share number.
- **08 — Portfolio construction & rebalancing:** no-trade regions (linear costs ⇒ no-trade region; Garleanu-Pedersen "aim portfolio" / partial adjustment), multi-period rebalancing, the Grinold-Kahn turnover ⇄ value-added frontier (≥87% of IR at half turnover; optimal turnover where frontier slope = round-trip cost), 4th-root capital scaling, the linear/piecewise-linear cost term inside the optimizer, drift-to-target and flows-as-free-rebalancing, tax-aware lot selection and loss-harvesting.
- **11 — Microstructure / market data & infrastructure:** latency types, order-book imbalance, BVC/Lee-Ready trade classification, colocation, SOR plumbing; Kyle's λ and market depth; the Roll/generalized-Roll/Huang-Stoll/Glosten-Harris/MRR spread-decomposition family; what genuinely needs co-location (market-making, latency arb, queue position, anti-detection) and what does not.

## To validate / watch-outs
- **Dated cost figures.** The ≈6¢/share manual vs. ≈1¢/share algorithmic split (Leshik, mid-2009), the QEPM 2020 commission/impact figures, the specific IB rate cards, and Carver's per-instrument cost table are all stale — re-pull current commissions, fees, and typical spreads before trusting any backtest cost number.
- **VWAP self-benchmarking.** If your order is a meaningful share of daily volume, VWAP-measured cost flatters to deceive (→0) while you still pay spread + impact, and it misses opportunity cost entirely (Grinold & Kahn). Prefer implementation shortfall against the decision price when you have the timestamps.
- **Square-root-law / I-Star constants are regime- and venue-specific.** Y (≈0.5), the Kissell I-Star coefficients (a1≈700, a2≈0.55, a3≈0.71 published), and the Almgren coefficients must be **fit to your own fills** — borrowed constants can be off by multiples. The exponent δ also varies by asset class (≈0.6 stocks, ≈0.5 Bitcoin, ≈0.4 vol markets). Volatility-adjust impact but cap a floor and stay conservative.
- **Peak impact is hard to escape by going slow.** The square-root law's horizon-independence (TQP) means *peak* impact depends only on Q, not execution speed — slowing down cuts *temporary* impact and timing risk (and the I-Star temporary/permanent split), but not the structural peak. Don't model slow execution as if it makes impact vanish.
- **Censored-fill bias.** Tick data shows fills, not the orders you never placed because they looked too expensive, so realized costs **underestimate** expected costs (Grinold & Kahn). Instrument opportunity cost explicitly.
- **Scheduled child orders are detectable.** TWAP/VWAP/POV streams are recoverable via autocorrelation/Fourier analysis even when randomized (Aldridge); randomization (skip/fuzz waves, child size ≤ top-of-book) raises the bar but does not confer invisibility. A POV algo that ignores its own volume can feed back destructively (a 2010-flash-crash ingredient).
- **Touch fills are not real fills.** Backtests that assume limit orders fill whenever price merely touches the limit overstate passive-fill rates and ignore queue position + adverse selection (Davey, p.42; Narang, p.162). The TQP martingale-wash result (`E[Δ](d)=0` with no signal) says passive execution is *not* free alpha; queue position and the autocorrelation regime decide whether it helps.
- **Opportunity/timing cost is invisible on fill reports.** The Plexus decomposition shows hidden timing + missed-trade costs can exceed visible impact + commission combined — instrument the *whole* path (decision → fill), not just the executed slices.
- **Don't over-charge either.** Overstating costs wrongly rejects good systems; calibrate assumptions to measured live slippage and revisit them as part of ongoing monitoring (Kaufman, p.118). Cross-check the *implied* transaction cost (slope of the turnover/value-added frontier) against your assumed round-trip cost and reconcile any gap (Grinold & Kahn).
