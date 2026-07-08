# 01 — Market Structure & Microstructure
*Trading System Knowledge Base · theme T01 · equities/ETF-weighted*
*Updated: includes Hasbrouck, Bouchaud et al., Kissell, Aldridge.*

**What this covers:** Who trades and why; how exchanges and order books actually work; order types and their exact semantics; the bid/ask spread and its component models; the econometrics of price formation (Roll, Glosten-Milgrom, Kyle, VAR/information-share); the empirical stylized facts of order flow (fat tails, long memory, LOB shape, the order-flow autocorrelation paradox); the dimensions of liquidity and price impact; and the operational implications for an equities/ETF trading system.
**Why it matters:** Every fill your system gets is the output of a matching engine populated by counterparties with different motives. Misunderstanding precedence, spread components, or adverse selection turns a backtested edge into a live loss. Order-type choice and venue routing are first-order determinants of realized cost. The same microstructure that sets your costs also leaks the most predictive ML features your system can consume (order-flow imbalance, price impact, cancellation signatures).
**Primary sources:** Harris, *Trading and Exchanges* (the backbone); Johnson, *Algorithmic Trading & DMA*; Narang, *Inside the Black Box*; Jansen; Chan, *Machine Trading*; Guo et al., *Quantitative Trading*; Leshik & Cralle; Hasbrouck, *Empirical Market Microstructure* (price-formation econometrics); Bouchaud, Bonart, Donier & Gould, *Trades, Quotes and Prices* (empirical stylized facts, LOB dynamics, impact); Kissell, *The Science of Algorithmic Trading and Portfolio Management* (venue/fee structure, intraday profiles); Aldridge, *High-Frequency Trading* (HFT mechanics, trade-sign classification); López de Prado, *Advances in Financial Machine Learning* Ch.19 (microstructural features); Tsay, *Analysis of Financial Time Series* (HF data artifacts); Hull, *Options, Futures & Other Derivatives* and Bennett, *Trading Volatility* (index/futures/variance mechanics).

---

## 1. Market participants & why they trade

Trade motive determines what each counterparty's presence implies for **adverse selection** — the risk that whoever fills your passive order knows something you don't (Narang, p.247).

- **Informed / value traders** trade on an estimate of fundamental value (or private information). They are the source of adverse selection: posting a bid reveals intent, and the counterparty may know more than you (Narang, p.247–250). Glosten-Milgrom (1985) and Kyle (1985) formalize that insiders alone force a positive bid-ask spread; the market maker earns ~0 expected profit and continuously updates quotes (Guo et al., p.12–15). **Two model families of asymmetric information** (Hasbrouck, p.21): **sequential-trade** models (Glosten-Milgrom — many one-shot informed traders arriving in sequence, each picking off a stale quote) and **strategic / continuous-auction** models (Kyle — a *single* strategic informed trader who optimally spreads his order over time to disguise it). Security value itself decomposes into a **common component** (cash-flow / resale value, shared and dominant) and a **private component** (idiosyncratic: investor horizon, risk tolerance, tax status) (Hasbrouck, p.2).
- **Value traders** supply **depth** and **resiliency** — they stand ready to trade when price diverges from fundamental value, pulling it back after uninformed order-flow imbalances (Harris, p.294, p.399–400).
- **Dealers / market makers** supply **immediacy**. Registered dealers (NYSE specialists, Nasdaq market makers) must post continuous *firm* two-sided quotes (Harris, p.281). They profit from the spread but bear inventory and adverse-selection risk.
- **Specialist / Designated Primary Market Maker** (NYSE/AMEX/options, one per stock): **affirmative obligations** = quote two-sided meaningful markets and maintain price continuity (trader of last resort); **negative obligations** = yield to public orders at the same/better price and don't fill the standing book (public-liquidity preservation) (Harris, p.496–499).
- **Hedgers** trade to offload risk, not to express a view — low adverse-selection counterparties.
- **News / technical traders** react to the *difference* between expectation and the actual report, not the raw number (Kaufman, p.207). Markets price *anticipation*: once the Fed cuts, traders price the *next* cut, which is why price patterns only *look* random (Kaufman, p.92–94).
- **Front-runners / order anticipators** detect and trade ahead of large orders — the reason large traders hide size (see §2, fragmentation). HFT order-anticipation and momentum-ignition strategies are the aggressive end (Jansen, p.63–69). Their footprints are observable in the message stream: **predatory-algo signatures** include quote stuffers, danglers, liquidity squeezers and pack hunters, detectable via quote-cancellation / limit / market-order rate features and TWAP-slice detection (front-running institutional schedules) (López de Prado, Ch.19.6). Order-anticipation is fed by the fact that large institutional orders are **split** ("metaorders") and executed over hours-to-days, leaving days-long serial correlation in signed order flow (López de Prado, Ch.19.6; TQP_p1, p.19).

**Block-trade asymmetry:** ~80% of large block trades are seller-initiated, because sellers can credibly cap order size (no short-sale ambiguity) and tell more convincing uninformed stories (Harris, p.332–333). A "block" rule of thumb is >¼ of ADV (NYSE statistical cutoff ~10,000 sh) (Harris, p.322–323).

---

## 2. Market types

**Three execution systems** (Harris, p.92–96) — the defining characteristic of any market:
- **Quote-driven:** dealers supply *all* liquidity; clients pick a dealer (OTC bonds, FX, classic Nasdaq).
- **Order-driven:** buyers and sellers trade directly via **order precedence + trade-pricing rules** (exchanges, ECNs, futures pits).
- **Brokered:** brokers search out concealed/latent liquidity (blocks, real estate).
- **Hybrid:** mixes all three. NYSE is order-driven + specialist quote obligation; Nasdaq is quote-driven + a duty to display/execute public limit orders.

Preferences diverge: dealers prefer quote-driven (less competition from public liquidity → higher margins); the cost-sensitive buy-side prefers order-driven (Harris, p.205). US Order Handling Rules (1997) + the Manning Rule pushed Nasdaq toward order-driven by forcing display of public limit orders and barring trading ahead of customers (Harris, p.216–217, 230). Public limit orders are economically equivalent to dealer quotes — both are standing offers to trade (Harris, p.310).

**Sessions:** **continuous** (trade anytime open) vs **call** (batch all orders at a called time). Many continuous markets open with a single-price call and use calls to restart after halts (Harris, p.89–91).

**Two canonical market designs** (TQP_p1, p.7–10): the **Walrasian (call) auction** collects firm bids/offers and clears them at the single price `p*` that *maximizes exchanged volume* `Q(p)=min[D(p),S(p)]`, where at the clearing point `D(p*)=S(p*)`. Modern markets instead run a **continuous-time double auction** mediated by a **limit order book (LOB)** — decentralized, usually with no designated market-maker, and observable in real time. The two designs are not interchangeable: as the inter-auction interval τ→0 the impact of trading changes shape (linear → square-root; see §6), so *trading frequency is itself a structural variable*.

**Lit vs dark:** lit venues display quotes; dark pools/ATSs do not. US equity trading is fragmented across 13+ venues with ~40% of volume in dark pools, all reporting to the consolidated tape (SIP) at varying latency (Jansen, p.90–93; Chan, p.164 cites >50 market centers, ~11 exchanges + ~40 dark pools; Aldridge Ch.3 estimates ~22% of volume dark, which carries no NBBO obligation). Securities trading is fundamentally a **double auction** matching best bid and offer for price discovery (Guo et al., p.1–4). The venue map now includes displayed markets, dark/grey pools, and two opposed fee models (Kissell Ch.1–2, p.21–22, 89–90; Aldridge Ch.3): **normal / maker-taker** venues charge the liquidity *taker* and pay the *maker* a rebate (e.g. NYSE); **inverted / taker-maker** venues pay the taker and charge the maker (e.g. Nasdaq BX). This creates the **rebate cost component** and a genuine routing conflict — whether a smart router optimizes for the *broker's* rebate or the *client's* execution quality.

---

## 3. The limit order book & order precedence

The **limit order book** is a queue of passive bids and offers ranked by precedence. Order-driven precedence is **hierarchical** (Harris, p.113–117):
1. **Price priority** — always primary, self-enforcing.
2. **Time precedence** — strict FIFO gives "pure price-time" (first-to-arrive at a price fills first).
3. **Display precedence** — shown orders beat hidden at the same price.
4. **Size / pro-rata precedence** — common in futures; rewards posting size at the level.
5. **Public-order precedence** (US stock floors) — members can't trade ahead of a public order at the same price.

**Price-time vs pro-rata** is a key fork. Price-time rewards layering and queue position (DMA, p.274; TQP_p1, p.54); pro-rata (e.g. eurodollar / short-rate futures, CME, CBOE) rewards posting *size* and removes the layering / queue-jump incentive, creating an oversizing-vs-overtrading tradeoff with high cancellation rates (Narang, p.121, 244–245; Aldridge Ch.3; TQP_p1, p.54). Queue placement is economically large: Tradeworx found ~1.7¢/share difference between being first vs last at a price, when *all* passive orders average ~−0.2¢/share (Narang, p.247–250).

**Resolution parameters & relative tick** (TQP_p1, p.49, 55): a book is parameterized by **lot size** `υ₀` and **tick size** `ϑ`. The economically decisive cross-sectional variable is the **relative tick** `ϑᵣ = ϑ/m` (tick as a fraction of price). Because the US tick is fixed at `ϑ = $0.01`, `ϑᵣ` spans ~`10⁻⁵` for high-priced names (e.g. PCLN ~$1000) up to large values for penny stocks — so "large-tick" vs "small-tick" stocks behave very differently (queue value, spread = 1 tick or not, LOB shape). **Iceberg / hidden orders** are a large share of real books: ≈30% of Euronext book volume is hidden, and the NASDAQ hidden fraction ranges 7–34% by stock (TQP_p1, p.55, Table 4.1).

**Small revealed, large latent liquidity** (TQP_p1, p.18, 59; TQP_p2, p.337–338): volume resting at the best quotes is only ≈`10⁻⁴` of market cap (≈`10⁻³` for small-tick stocks), whereas *daily* turnover is ≈0.5% of cap (and has roughly doubled 1995→2015). The visible LOB therefore shows a tiny fraction of true supply/demand; most is **latent** — unexpressed intentions held back to avoid signalling and impact. Because revealed liquidity is so scarce, large orders *must* be fragmented into metaorders worked over days, and the equilibrium price is "an ever-moving target" that never instantaneously clears supply and demand (TQP_p1, p.19). Modelling the impact of metaorders therefore requires the *latent* book, not the visible one (TQP_p2, p.337–338).

**Matching procedure** (replicate exactly for any simulated book; Harris, p.117–119):
1. Rank both sides by precedence.
2. Match the highest-ranked buy against the highest-ranked sell.
3. A trade occurs only if **buyer's bid ≥ seller's ask**.
4. Fill the smaller order fully; carry the remainder to the next order.
5. Continue until the books no longer overlap (a spread remains).

**Trade-pricing rules** (Harris, p.119–122):
- **Uniform / single-price** — call auctions clear *all* trades at one market-clearing price (supply = demand), maximizing volume.
- **Discriminatory** — continuous auctions execute each trade at the *standing* order's price.
- **Derivative** — crossing networks price off another market (e.g. POSIT at the primary-market bid/ask midpoint).

**Tick size** is a first-order structural variable. Too small weakens time precedence and kills displayed size (observed after US 2001 decimalization cut the tick from 1/16 = 6.25¢ to 1¢); too large makes price-improvement expensive (Harris, p.114–117). Smaller ticks *raised* specialist participation by cheapening stepping in front of the book (Harris, p.500). **Price clustering:** quotes concentrate on round numbers (whole > half > quarter); tactical edge is to place limits just *inside* a round-number cluster (Harris, p.91). **Book depth tiers:** L1 = best bid/ask; L2 = per-market-maker depth + recent sizes/times; L3 = enter/modify quotes (market-makers only) (Jansen, p.97).

---

## 4. Order types and exact semantics

Encode these precisely in any backtest or execution layer (Jansen, p.90; Harris):

- **Market order** — execute immediately at best available; *walks the book* if size > quote (SuccessfulAlgo, p.18). Crosses the spread, pays immediacy, no price control.
- **Limit order** — price-conditional; trade only at the limit or better. Provides liquidity; bears non-execution risk and adverse selection.
- **Marketable limit order** — a limit priced at/through the opposite quote; executes immediately against the best standing order like a market order but with a price cap (Harris, p.316/304).
- **Stop order** — dormant until price trades through a trigger, then becomes a **market** order. Used for exits/breakouts.
- **Stop-limit** — on trigger becomes a **limit** order (avoids slippage but risks non-execution on a gap).
- **IOC (immediate-or-cancel)** — fill what's available now, cancel the rest.
- **FOK (fill-or-kill)** — fill the *entire* order immediately or cancel.
- **AON (all-or-none)** — fill in full or not at all (no partials), but may rest.
- **MOO / MOC (market-on-open / -on-close)** — execute in the opening/closing auction. The close is the highest-volume "evening-up" point, required for mark-to-market, margin, and NAV (Kaufman, p.229–230).
- **Pegged order** — limit price tracks a reference (e.g. NBBO midpoint). High latency kills reactive pegging; prefer pre-positioned layering when remote (DMA, p.274).
- **Iceberg / hidden order** — displays only a slice of true size; loses display precedence on the hidden portion (Harris, p.114; Narang).
- **ISO (intermarket sweep order)** — exploits the SIP-vs-direct-feed lag (~0.5 ms) for hide-and-light edges (Chan, p.166, 172).
- **Routed / conditional orders** — smart order routing (SOR) and liquidity-seeking algos aggregate fragmented liquidity (DMA, p.146, 208; Leshik, p.14–15).

**Aggressive can *add* liquidity, passive can *remove* it:** an aggressive order that pushes price toward fair value adds liquidity; a passive accumulation away from fair value removes it (Narang, p.246–247).

**A limit order is a free option written to the market** (TQP_p1, p.46): by posting, you grant other participants the right (not obligation) to trade against you at your price; informed traders exercise that option precisely when it hurts you (adverse selection, §5). The two order types carry mirror-image risks: a **market order's** risk is *slippage* (walking the book), a **limit order's** risk is *non-execution* (Aldridge Ch.3). This option framing is why passive fills are systematically adversely selected and why posted liquidity evaporates in turbulence.

---

## 5. The bid/ask spread — components & models

The **inside spread** = highest bid − lowest ask; always ≤ the narrowest single-dealer spread, usually far tighter (Harris, p.280–281). The spread is itself a transaction cost, larger for illiquid assets (SuccessfulAlgo, p.20). Three components:
1. **Order-processing** — fixed costs of providing the quote.
2. **Inventory** — compensation for holding unwanted positions.
3. **Adverse selection** — compensation for trading against the informed.

**Efficient price as a martingale** (Hasbrouck, p.11, 27): the unobserved "efficient" (fundamental) price `mₜ` follows a random walk `mₜ = mₜ₋₁ + uₜ`, and observed trade prices deviate from it only via spread / microstructure effects. Formally, a sequence of conditional expectations of terminal value on an expanding information set is a martingale — this is the econometric backbone that lets you *decompose* an observed transaction-price series into a permanent (information, random-walk) component and a transitory (microstructure) component.

**Glosten-Milgrom (adverse-selection component)** (Harris, p.319–321): if the next trade is informed with probability *P* and the informed value is *V ± E*, the dealer quotes
- **Ask** = *V + P·E*, **Bid** = *V − P·E*
- **Adverse-selection spread component = 2·P·E** — wider when informed-trader probability or information magnitude is high.

**Glosten-Milgrom, Bouchaud's notation** (TQP_p1, p.17; TQP_p2, p.299–303): with a fraction `φ` of perfectly-informed traders predicting a jump `±J`, a binding quote that gets picked off implies a long-term price impact `R∞ = φ·J` and a **break-even spread `s = 2·φ·J`** (≈ `2·φ·σ` when the informed signal scales with volatility). Market-making is profitable only if `s/2 > R∞`. Crucially, the market-maker's P&L per round-trip is **heavily negatively skewed** (skewness `ς ≈ −1/√φ`): profitable *on average* but exposed to rare, huge losses when an informed trade arrives — "akin to selling insurance." This is *why* posted liquidity is fragile and vanishes in turbulence. For the spread to stay bounded as the horizon grows, the informed fraction must decay at least as `φ ∝ 1/√T` (empirically `φ ≈ 1%` at `T = 1 day`); if `φ` is too large no break-even spread exists and market-makers withdraw → **liquidity drought / breakdown** (TQP_p2, p.303, 315).

**Two volatility-relevant components** (Harris, p.413–414): the **adverse-selection (permanent)** component reflects information inferred from order flow → contributes to *fundamental* volatility; the **transaction-cost (transitory)** component causes **bid/ask bounce** → contributes to *transitory* volatility.

**Roll (1984) bid-ask bounce** (Guo et al., p.99; Hasbrouck, p.12; Tsay, p.235–236): the "basic black dress" of microstructure. The dealer posts bid/ask symmetrically around the efficient price `mₜ` to recover the per-trade cost `c`: `bₜ = mₜ − c`, `aₜ = mₜ + c`, so the observed trade price is `Pᵢ = P*ᵢ + c·Iᵢ` (Hasbrouck writes `pₜ = mₜ + c·qₜ`), where `2c` = spread and `Iᵢ = qₜ = ±1` is the i.i.d. buy(+ at ask)/sell(− at bid) indicator, assumed serially independent and independent of the value innovation `uₜ`. Then
- `Var(ΔPᵢ) = S²/2` (with `S = 2c`), `Cov(ΔPᵢ, ΔPᵢ₋₁) = −c² = −S²/4`, and `Cov(ΔPᵢ, ΔPᵢ₋ⱼ) = 0` for `j ≥ 2` → `ρ₁ = −0.5`, `ρⱼ = 0` (j>1).
- This recovers the **negative first-order (MA(1)) autocorrelation** of price changes (Niederhoffer-Osborne 1966) — a microstructure artifact, *not* an EMH violation — and shows naive GBM estimation on trade prices is inconsistent (Guo et al., p.17–20). It explains apparent short-horizon mean reversion in high-frequency prices.
- **Effective-spread estimator:** invert the autocovariance to recover an implied spread directly from price data — `c = √(−Cov[Δpₜ, Δpₜ₋₁])` — which is especially useful for rarely-traded instruments with no reliable central book (e.g. bonds) (López de Prado, Ch.19.3). For venues with *no* central book at all (corporate-bond BWIC), use **high-low spread estimators** — Corwin-Schultz (and Parkinson/Beckers high-low volatility), flooring any negative spread estimate at 0 (López de Prado, Ch.19.3). Caveat: the i.i.d.-sign assumption is false in real, autocorrelated order flow (see §6 long memory), so treat recovered spreads as approximations.

**Glosten-Harris** decomposes the spread into a permanent (adverse-selection) and a transitory (order-processing) part — the empirical generalization of the Roll/Glosten-Milgrom split above (Harris, p.413–414).

**MRR model — spread, impact and volatility are one coin** (Madhavan-Richardson-Roll; TQP_p2, p.309–315). The traded price is a martingale driven by the *surprise* in order-flow sign: `pF,t − pF,t−1 = G*·(εₜ − ε̂ₜ) + ξₜ`, where `εₜ = ±1` is the trade sign, `ε̂ₜ` its conditional forecast, and `ξₜ` is public news. From this single equation:
- **Spread** `s = 2·G*` (the spread is twice the impact of an unforecastable trade).
- **Response function** `R(ℓ) = (s/2)·(1 − C(ℓ))`, where `C(ℓ)` is the sign-autocorrelation at lag ℓ; the *permanent* impact is `R∞ = G* = s/2`.
- **Per-trade volatility** ties directly to the spread: `σ̃²∞ = ¼·(1 − C(1)²)·s² + Σ²`.
These relations hold remarkably well across ~120 stocks and within-stock through time, enforced by competition among market-makers (TQP_p2, p.312–315). Operationally: **spread, price impact and short-horizon volatility are not three independent quantities — they are three views of the same adverse-selection process.**

**Price discovery & the trade/quote VAR (information share)** (Hasbrouck): because the efficient price is a latent martingale (above), price discovery is estimated econometrically from a **vector autoregression (VAR) of trades and quote revisions**. Two workhorse decompositions:
- **Hasbrouck information share** — in a cointegrated system of prices for the *same* asset across venues (an error-correction / **VECM** with a common stochastic trend), each venue's *information share* is its contribution to the variance of innovations in the common efficient price. It answers "where does price discovery happen?" (lit vs dark, primary vs satellite venue, futures vs cash).
- The **VAR / VECM impulse responses** also yield the permanent (information) vs transitory (microstructure) impact of a trade, generalizing the Roll/Glosten-Harris split to autocorrelated, multi-lag order flow. This is the rigorous version of "how much of a price move was information vs noise," and the principled way to measure **lead-lag** between an index/futures market and its cash market (cf. §7 "tail wags the dog").

**Spread compression (cost regime):** electronic trading (STP), tighter ticks, and competition have collapsed spreads (DAX intraday ~6–8 pts 20 yrs ago vs ~0.9 now; Dow ~8 pts vs ~1), lowering the breakeven hurdle for intraday systems (BestLoser, p.39–40; Guo et al., p.4).

---

## 6. Liquidity dimensions & price impact

Liquidity is "the ability to trade large size quickly, at low cost, when you want to trade" — the object of a **bilateral search** in which exchanges act as search engines that lower search cost (Harris, p.394–396). Narang sharpens it: liquidity = *immediate availability to transact at a fair price* — **not** volume and **not** book size; high volume ≠ high liquidity (Flash Crash; Aug 2007) (Narang, p.246).

**Four facets** (Harris, p.312; the same triad appears in Hasbrouck, p.3 as **depth, breadth, resilience** — "trade a large amount without moving price much; perturbations die out quickly"):
- **Immediacy** — how fast you can trade (supplied by dealers).
- **Width (spread)** — immediacy cost for small orders.
- **Depth** — cost of large orders; supplied by value traders.
- **Resiliency** — how fast price recovers after *uninformed* pressure; supplied by value traders standing ready when price ≠ fundamental value (Harris, p.399–400, 403). Hasbrouck operationalizes resilience for the *whole book* via price-impact and random-walk-variance measures (Hasbrouck, p.3).

**Price impact / walking the book:** liquidity is thin at the touch — even AAPL top-of-book ~189 shares; orders larger than quote size walk the book (Chan, p.159, 177). Small NBBO quotes are often HFT sniffers/queue-holders. **Market depth is the key price-impact indicator** (Jansen, p.97).

**Kyle's λ and the family of illiquidity proxies** — price impact per unit of *signed* order flow is the central liquidity measure for econometrics and as an ML feature (López de Prado, Ch.19.4; price-impact is "second-generation" microstructure, modelling the *strategic / illiquidity* dimension):
- **Kyle's λ** — regress the price change `Δp` on signed volume `bₜ·Vₜ`; the slope `λ` is the price impact of order flow and `λ⁻¹` is a direct measure of market depth / liquidity. Larger λ = more fragile market.
- **Amihud's λ** — `|return| / dollar-volume` per bar; a cheap, daily-data illiquidity proxy.
- **Hasbrouck's λ** — a Bayesian (Gibbs-sampler) estimate of price impact from signed-dollar-volume on TAQ data.
All three are illiquidity proxies that carry a **risk premium** (illiquid assets earn more) and are usable directly as predictive features. In the LOB micro-foundation (TQP_p2, p.343–344), Kyle's λ for an *infrequent Walrasian auction* is `Λ⁻¹ = ρ₊ˢᵗ(0) + ρ₋ˢᵗ(0)` — the sum of the stationary marginal supply/demand densities at the clearing price — making the link from "depth of book at the touch" to "λ" explicit.

**Empirical impact law: linear vs square-root** (TQP_p2, the central result of the impact chapters). Model the **marginal supply/demand (MSD)** densities `ρ₋ = ∂ₚS`, `ρ₊ = −∂ₚD` around a reference price; between auctions they evolve by deposition `λ±`, cancellation `ν±`, and price-revision diffusion: `∂ₜρ± = D·∂²ₓₓρ± − ν·ρ± + λ±` with diffusion constant `D = ½(Σ² + σ²·Var[βᵢ])` (TQP_p2, p.340–342; close in spirit to the Santa Fe zero-intelligence model but with continuous price revision). The trading *frequency* then determines the impact shape:
- **Infrequent (Walrasian) auctions → LINEAR impact.** The stationary MSD is finite at the clearing price, so impact is Kyle-linear: `I(Q) = Λ·Q`. An exponential book gives `Λ = Δ/(2V*)` and the full law `I(Q) = Δ·sinh⁻¹(Q/2V*)` — linear for small Q, logarithmic for large Q (TQP_p2, p.345).
- **Frequent (continuous) auctions → SQUARE-ROOT impact.** As the inter-auction time τ→0, liquidity has no time to rebuild near the price, so the MSD develops a characteristic **V-shape** that vanishes *linearly* at the traded price: `ρ±ˢᵗ(x) ≈ L·|x|` near `x = 0` (TQP_p2, p.346–347). Kyle's λ then **diverges** as `Λ ∝ 1/√τ` — the market becomes *fragile* in the high-frequency limit. Impact crosses from linear (`Q ≪ V*`) to square-root (`Q ≫ V*`) with `V* = L·D·τ`; as τ→0 the linear zone vanishes and one gets **pure √-impact**: `I(Q) ≈ √(2Q/L) = √2·σ_T·√(Q/V_T)`, i.e. the empirical "square-root law" with `L = V_T/σ_T²` (TQP_p2, p.348–349). Confirmed on Bitcoin LOB data (linear MSD / quadratic cumulative book near the mid) (TQP_p2, p.351).
- **The fragility paradox:** more-frequent trading, *nominally* more efficient, makes prices **more** fragile (λ larger, impact super-linear in the high-frequency limit) (TQP_p2, p.351–352).

**Metaorder impact dynamics & no-manipulation** (TQP_p2, p.357–361): for a metaorder with execution flux `j(t)`, the price path solves a self-consistent reaction-diffusion integral equation; for small flux it reduces to a **continuous-time linear propagator with decay exponent β = 1/2** (an inverse-√-time impact-decay kernel), while for large flux it stays exactly √-shaped and depends only on *executed volume* `q(t)`, not the schedule. Post-trade **decay** after a metaorder of duration T: `I(Q, t>T)/I_peak = (√t − √(t−T))/√T` — an infinite initial decay slope followed by a slow `(T/t)^{1/2}` tail (partial reversion, never full). The framework is provably **free of price manipulation**: any closed round-trip has cost `C ≥ 0`, so trading is only ever justified by a real signal — a useful sanity constraint on any execution or alpha model.

**Trade-side classification** for TCA on others' trades, since raw ticks carry no buy/sell flag. The methods, in rough order of sophistication (Harris, p.423; Aldridge Ch.4; López de Prado, Ch.19.3):
- **Tick rule** — `bₜ = sign(Δpₜ)`, carrying the prior `bₜ` when `Δpₜ = 0`. Simple but accurate: ~77% on equities, ~86% on E-mini (Aldridge Ch.4). The whole **first generation of price-only microstructural features** is built from the sign series `{bₜ}`: Kalman-filtered expectation, structural breaks, entropy, runs-test t-values, and fractional differentiation of cumulative signs (López de Prado, Ch.19.3).
- **Quote rule** — classify vs the prevailing quote midpoint.
- **Lee-Ready** — hybrid: closer to bid → seller-initiated; closer to ask → buyer-initiated; at the midpoint → fall back to the tick rule (last price change; uptick / zero-uptick = buy). Biases: overstates cost (assumes pure liquidity demand) and can't aggregate split fills; the historical short-sale uptick rule degraded equity accuracy.
- **Bulk volume classification (BVC)** — probabilistic assignment of buy/sell *fractions* to volume bars on a *volume clock*, ~90% accurate, and the input to VPIN (below).

Prefer exchange-provided trade-direction flags where available.

**Consolidation vs fragmentation:** the **order-flow externality** (a network externality — liquidity attracts liquidity) makes markets consolidate naturally and gives incumbents a moat (Harris, p.526–528). Yet markets fragment because *traders differ* in size, information, patience, access, and creditworthiness (Harris, p.530–533): large traders hide orders and fear front-running; informed traders prefer anonymous consolidated venues; impatient traders prefer dealers; patient traders prefer order-driven books with time precedence.

---

## 7. Empirical stylized facts & order-flow long memory

The empirical regularities of price and order-flow series (Bouchaud et al., *Trades, Quotes and Prices*; cross-references the statistics in theme 02). These are *robust across assets and decades* and constrain any realistic microstructure or backtest model.

**Price / return stylized facts:**
- **Fat (power-law) tails.** The unconditional distribution of high-frequency returns is strongly **leptokurtic** with power-law tails (tail exponent ≈ 3–4), far from Gaussian; aggregation toward Gaussian is slow.
- **Volatility clustering.** Squared / absolute returns have **long-ranged, slowly-decaying autocorrelation** — large moves cluster (the empirical fact GARCH/stochastic-vol models exist to capture).
- **Near-efficiency (near-unpredictability) of signed returns.** The *sign* of price changes is almost unpredictable — return autocorrelation decays to near-zero within seconds — so prices are *statistically* close to a martingale (consistent with Hasbrouck's efficient-price assumption, §5), even though the *generating process* is anything but i.i.d.

**The order-flow autocorrelation paradox (LONG MEMORY).** The signed order-flow series (the `±1` trade-sign sequence `εₜ`) is the opposite of the return series: its autocorrelation `C(ℓ)` decays as a **slow power law** `C(ℓ) ∼ ℓ^(−γ)` with `γ < 1` — *long memory* persisting for **thousands of trades / many days**. The dominant cause is **order-splitting**: large metaorders are sliced and worked over time, so consecutive trades share the same sign (Lillo-Mike-Farmer mechanism). This creates a genuine paradox:

> If order flow is *persistently autocorrelated* (highly predictable) but *prices are nearly unpredictable*, how do the two coexist without an obvious arbitrage?

The resolution: the market is in a **fine-tuned dynamic balance** between *liquidity takers* (whose persistent, sign-correlated flow would push price in a predictable trend) and *liquidity providers* (who, anticipating this, lean against it by skewing quotes and refilling the depleted side of the book). The persistent component of impact must be exactly offset by a **decaying impact propagator** (the `β = 1/2` kernel of §6) so that the *net, observable* price remains a martingale. Equivalently: **permanent impact is small and concave (√-law), transient impact is large but mean-reverting**, and the two are tuned so signed returns are unpredictable while signed flow is not. Practical consequences:
- **Naive Roll / Glosten-Milgrom estimators are biased**, because they assume i.i.d. signs; the true sign process has long memory (TQP; cf. §5 caveat).
- **Order-flow imbalance is a real, persistent signal** (the long memory is *why* OFI predicts short-horizon returns at all — see theme 10) — but it is **already largely impounded into price** via the propagator, so capturing it requires beating the impact-decay clock, not merely detecting the imbalance.
- Any backtest that models order flow as serially independent will mis-estimate both impact and the achievable edge.

**LOB shape & queue dynamics (empirical):** the average shape of the book is **hump-shaped** (density rises from the touch to a peak a few ticks in, then decays); queue sizes, lifetimes, and cancellation counts are heavy-tailed / **power-law** distributed, especially for small-tick stocks. The visible book is a thin, fast-refilling skin over the latent book (§3), which is why depth at the touch is a poor proxy for true available liquidity (reinforces "liquidity ≠ volume," §6).

---

## 8. HF data artifacts, informed-trading proxies & microstructural ML features

**High-frequency data properties** (Aldridge Ch.4; Tsay Ch.5) — naive return statistics are contaminated unless you account for:
- **Voluminous & irregularly time-spaced.** Trades arrive at random times; equally-spaced sampling (last-tick or interpolated) discards information. Prefer **event clocks** — volume, dollar, or price-*duration* clocks (also the basis of Tsay's ACD duration models).
- **Bid-ask bounce.** Tick-by-tick returns show ≈ **−40% first-order autocorrelation** purely from quotes flipping between bid and ask (Aldridge Ch.4) — the same Roll/MA(1) artifact derived in §5. De-noise with the **midquote** or a size-weighted midquote rather than trade prices.
- **Non-normality.** Trade-price returns are non-Gaussian but fit a normal best out to ~4σ (Aldridge Ch.4).
- **Nonsynchronous trading** (Tsay, p.232–233; Lo-MacKinlay). Because last-trade times differ across stocks, a more-frequently-traded stock A *appears* to **lead** a less-traded stock B even when they are independent — producing spurious lag-1 *cross*-correlation, spurious *portfolio* serial correlation, and even spurious *negative* autocorrelation for a single stock (governed by the no-trade probability π). A lead-lag signal must clear this bar before it is real (cf. §5 information-share for the rigorous test).

**Informed-trading proxies (sequential-trade / "third-generation" features)** (López de Prado, Ch.19.5):
- **PIN (Probability of Informed Trading)** `= αμ / (αμ + 2ε)`, where α = probability of an information event, μ = informed order rate, ε = uninformed order rate. The market-maker prices the spread as the premium for the *option of being adversely selected* — the direct empirical analogue of Glosten-Milgrom (§5).
- **VPIN (volume-synchronized PIN)** `≈ mean|V⁺_τ − V⁻_τ| / V` over n equal-**volume** bars (signs from bulk volume classification, §6). A high-frequency, volume-clock estimator; evidence as a *volatility predictor* is mixed, but it is widely used and notably **flagged the May 2010 Flash Crash** in advance.

**Defining "information" microstructurally** (López de Prado, Ch.19.7): train a classifier to predict a market-maker's P&L from features `X` (VPIN, λ, cancel rates…); define microstructural information `φ_τ = F[−L_τ]`, the CDF (via KDE) of the *negative cross-entropy loss* of out-of-sample predictions. **Rising cross-entropy loss = market-makers being adversely selected by informed traders** — exactly the accumulating-prediction-error mechanism that preceded the Flash Crash. (Note: t-values of microstructural regression estimates are usually *more* informative than the point estimates, being rescaled by estimation-error std — López de Prado, Ch.19.4.)

**Beyond-theory microstructural features** (López de Prado, Ch.19.6) — among the most predictive ML inputs; primary source is **FIX-message data** (cancellations, full book, aggressor side, partial fills):
- **Round-trade-size frequency** — human "GUI/mouse" traders cluster on round lots {5, 10, 25, 50, 100, 200…}; a *high* round-size share signals human conviction / trending, a *low* share signals algos / sideways markets.
- **Quote-cancellation / limit / market-order rates** — signatures of predatory algos (quote stuffers, danglers, liquidity squeezers, pack hunters; §1).
- **TWAP-execution detection** — spot the regular slicing of an institutional schedule and front-run it.
- **Option-trade information** — the put-call-implied stock price; expensive calls outperform expensive puts by ~50 bp/wk.
- **Serial correlation of signed order flow** — the order-splitting long memory of §7, persisting for days, used directly as a feature.

---

## 9. Implications for a trading system

- **Order-type choice is a cost decision.** Use marketable/market orders only when immediacy outweighs the spread you pay; prefer limit orders to *earn* the spread, accepting non-execution and adverse-selection risk.
- **Passive fills are adversely selected.** A resting limit order fills *because* someone wanted to trade against it — expect the average passive fill near −0.2¢/share, with queue position worth ~1.7¢ (Narang, p.247–250). Model fills conditionally, not optimistically.
- **Replicate the matching engine exactly** (§3) in simulation, including price-time vs pro-rata, hidden/iceberg display rules, and (for futures) implied-out calendar-spread quotes that get queue priority over outrights (Chan, p.184).
- **Latency dictates tactics.** Remote venues add tens of ms; co-location reduces it. High latency kills reactive pegging — prefer pre-positioned layering and catching (DMA, p.274). SIP lags direct feeds ~0.5 ms (Chan, p.166).
- **Route to the NBBO.** Reg NMS Rule 611 forces marketable orders to the best *displayed* protected quote; Rule 610 bars locked/crossed markets (Chan, p.164, 211; Jansen, p.90–93). Liquidity aggregation via SOR is mandatory in a fragmented tape.
- **Capacity is a liquidity constraint.** Negligible market impact in liquid names is a genuine retail edge (SuccessfulAlgo, p.10–12), but thin depth at the touch caps size before you walk the book. Size positions to book depth, not ADV alone.
- **ETF microstructure is benign.** Index/ETF dealers quote tight because almost no one is informed about *whole-market* value (low adverse selection), volume turns inventory fast, and one trade clears vs many component trades (Harris, p.489). ETFs add intraday trading, fewer taxable events, and no redemption-cash drag (Harris, p.492). Index/futures markets *lead* cash ("tail wags the dog") — watch the index for direction (Harris, p.489, 562); the rigorous way to quantify that lead is the trade/quote VAR information share (§5, Hasbrouck).
- **The intraday volume profile is "J"-shaped, not "U"-shaped, and event-day-dependent** (Kissell, p.67–76). Volume is now far heavier into the **close** (index funds, ETFs, transparent closing auctions) than at the open; spreads and volatility are *elevated and persistent at the open* (weaker price discovery without specialists) and decline into the close. Small caps carry higher spreads/volatility and trade more in auctions. The **coefficient of variation of interval volume** is a key, under-used liquidity-risk input to market-impact models (Kissell, p.72–73). **Special-event days** (FOMC, triple/quadruple witching, earnings, index-reconstitution changes, month/quarter-end, holidays, early closes) shift volume sharply — index-change days in particular dump huge volume into the **closing auction** (Kissell, p.73–76). Calendar-aware volume curves, not a static U-shape, should drive any scheduling algo.
- **Maker-taker vs taker-maker fees are a real routing lever** (Kissell, p.21–22, 89–90; Aldridge Ch.3). Net cost = spread paid/earned ± rebate; a smart router that optimizes the *broker's* rebate rather than the *client's* fill is a measurable conflict — audit realized rebate capture vs price improvement, don't assume best-ex.
- **Flash-crash lesson: algorithms do exactly what they are programmed to do** (Kissell, p.76–85). Build safeguards (max participation, price collars, kill switches) — but not so strict that they block trading in fast *normal* markets. The accumulating-adverse-selection mechanism (rising market-maker cross-entropy loss / VPIN, §8) is the early-warning signal worth monitoring.

**Index, futures & variance-product mechanics (operational, equities/ETF context)** — Hull, *Options, Futures & Other Derivatives*; Bennett, *Trading Volatility*:
- **Stock-index futures & the cash-and-carry basis** (Hull). The fair futures price is `F = S·e^((r − q)·T)` (q = dividend yield), so the basis is a pure carry quantity; index/futures *lead* cash because the future is the cheaper, more liquid expression of a whole-market view (reinforces §7 lead-lag and Harris p.489). Index arbitrage enforces the relation but transmits stress (program-trading cascades).
- **Variance / volatility indices are now variance-swap-based, not ATM** (Bennett, p.49). The VIX methodology moved from the old ATM-implied VXO to a model-free **variance-swap** strip on 22-Sep-2003 (new VIX ≈ 1-month vs old ≈ 1.5-month); VSTOXX, VSMI, VFTSE, VNKY, VHSI are all variance-based (VIMEX is an exception). Relevant to microstructure because these are *tradeable, hedged* instruments whose dealer flow hits the cash market.
- **Variance-swap hedging flow pins / moves the cash close** (Bennett, p.55–56). Because the intraday delta of a variance swap resets to zero daily, dealers hedge at the **cash close**: clients **net buying** variance *suppresses* the close, **net selling** *exaggerates* it (rule of thumb — hedge flow pushes in the direction that makes the crowded trade *less* money). Flows can run into hundreds of millions/day, with basis risk (payout on cash close, hedged with futures). A material, predictable closing-auction order-flow source worth modelling alongside the J-shaped profile above.
- **Long-gamma delta-hedging can "pin" an *illiquid* single stock (not a liquid index) to a strike into expiry** (Bennett, p.43) — e.g. a convertible long-gamma position pinning a name for months. **CBOE implied-correlation indices** (ICJ/JCJ/KCJ) track dispersion-implied correlation on the top-50 S&P names (Bennett, p.72). **Single-stock option liquidity facts:** liquidity fades beyond ~1–2Y; OTM more liquid than ITM; low-strike puts more liquid than high-strike calls (Bennett, p.14).

---

## Cross-references
- **02 — Statistical Properties of Returns:** leptokurtic / power-law-tailed high-frequency returns reverting slowly to Gaussian, volatility clustering (long-ranged abs-return autocorrelation), near-unpredictability of signed returns vs **order-flow long memory** (§7), J- vs U-shaped intraday volume, short-lived return autocorrelation (Guo et al.; Leshik; Bouchaud et al.; Tsay).
- **09 — Transaction Costs & Execution:** trade-sign classification (tick / quote / Lee-Ready / BVC), implementation shortfall, **square-root market-impact law and the β=1/2 impact-decay propagator** (§6, Bouchaud et al.), metaorder scheduling, no-manipulation cost constraint, SOR, maker-taker/rebate routing, calendar-aware volume curves (Kissell), slippage modeling.
- **10 — Order Flow & Imbalance Edges:** signed order-flow imbalance (OFI) as a persistent (long-memory) signal already partly impounded via impact; Kyle/Amihud/Hasbrouck λ and VPIN as informed-flow proxies; bellwether/index-cash lead-lag measured via the Hasbrouck information share.
- **05 — Index Products & ETFs:** create/redeem mechanics, price- vs cap-weighting, divisors, total-return benchmarks; **index-futures cash-and-carry basis** `F = S·e^((r−q)T)`, variance-swap-based vol indices and closing-auction hedge flow (Hull; Bennett).
- **11 (or vol theme) — Volatility & Options Microstructure:** variance-swap mechanics, delta-hedge pinning, implied-correlation indices, single-stock option liquidity (Bennett; Hull).

## To validate / watch-outs
- **Dated venue/regulatory specifics.** Exchange tickers, ATS names (Island, Instinet, BRUT), HFT volume shares (~55%), and SIP-lag figures drift; re-verify against current Reg NMS / venue maps before encoding.
- **Roll/Glosten-Milgrom assumptions are stylized.** I.i.d. order signs and constant *c* break in real, autocorrelated order flow; treat recovered spreads as approximations, not ground truth.
- **Lee-Ready biases.** Overstates cost and mishandles split fills; prefer exchange-provided trade-direction flags where available.
- **Pro-rata vs price-time changes optimal posting behavior** — backtests must match the *actual* venue's precedence rule or queue-position assumptions will be wrong.
- **"Liquidity ≠ volume"** — do not size or model impact off ADV alone; book depth at the touch is the binding constraint (Flash Crash precedent).
- **Folklore asides** (gap-fill %, ~90% of daily highs/lows in first 90 min, round-number/limit-up traps) are unverified incidentals from BestLoser — validate empirically before use as features or risk parameters.
- **Square-root impact law is empirical, not universal.** Coefficients (the `Y` in `I ≈ Y·σ·√(Q/V)`) drift by asset class, regime, and metaorder definition; the linear→√ crossover `V*` and the `β=1/2` decay are stylized facts that must be **re-fit on your own fills**, not assumed. The reaction-diffusion derivation assumes a specific MSD dynamic; treat it as a strong prior, not ground truth.
- **Order-flow long memory ≠ free alpha.** The persistence of signed flow is largely already in the price via the impact propagator; naive "follow the imbalance" strategies pay the impact they detect. Verify net-of-impact edge, and never model order flow as i.i.d. in a backtest (it biases both impact and PnL).
- **PIN / VPIN are contested as volatility predictors.** Evidence is mixed and estimation is sensitive to the volume-bar size and trade-sign classifier; use as *one* feature with proper out-of-sample t-values (which are more reliable than point estimates), not as a standalone toxicity gate.
- **Dated VIX / fee / venue figures.** The 2003 VIX-methodology change, specific rebate schedules, dark-volume % (~22%), hidden-order fractions, and inverted-venue names all drift — re-verify against current exchange specs before encoding. Same caution as the dated Reg-NMS/ATS specifics above.
- **Hasbrouck information share is not identified uniquely** when venue innovations are contemporaneously correlated (it yields an upper/lower-bound range depending on Cholesky ordering). Report the bounds, or use a structural/Gonzalo-Granger component share, before claiming "venue X leads venue Y."
