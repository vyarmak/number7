# 14 — Fundamental Analysis & Valuation
*Trading System Knowledge Base · theme T14 · equities/ETF-weighted*

*Updated (pass 3): integrated Gray & Carlisle, Quantitative Value — the value+quality screen (M-score, F-score, Altman/Ohlson, EV/EBIT).*

**What this covers:** Why fundamentals matter to a *quant* (they ARE the value / quality / profitability factors — cross-ref 04); the Koller value-driver logic (`Value = f(ROIC, growth, WACC)`, economic profit `= IC·(ROIC − WACC)`, the key-driver and value-driver formulas); enterprise-DCF mechanics end-to-end (NOPAT, invested capital, free cash flow, WACC via CAPM, continuing value) — enough to *compute the inputs*; reading the financial statements for the right inputs and the accounting red flags; relative valuation / multiples (E/P, EV/EBITDA, FCF yield, P/B) and their pitfalls; **turning fundamentals into tested factors** — Tortoriello's empirical Q1/Q5 magnitudes for the signals that actually predicted equity returns (FCF/price, EV/EBITDA, ROIC, economic profit, capital allocation, accruals/red flags) and the multifactor combination; **the Gray–Carlisle *Quantitative Value* algorithm** — a complete, turnkey four-step fundamental stock-selection screen (avoid permanent loss → quality → price → corroboration → assemble & backtest) with every formula (Beneish M-score, accruals STA/SNOA, Altman Z, Ohlson O, Campbell-Hilscher-Szilagyi PFD, gross profitability GPA, the Piotroski/FS_SCORE, EV/EBIT "acquirer's multiple") and the ~1974–2011 empirical magnitudes; fundamental factor models (the QEPM fundamental-factor regression, z-score compositing); and the practical pipeline point-in-time fundamentals → factor scores → cross-sectional ranking.

**Why it matters:** For a systematic equities/ETF book, "fundamental analysis" is **not** stock-picking narrative — it is the *raw material of the value, quality, and profitability factor families*. The valuation theory tells you *which* statement items carry signal and *how to combine them* so high = good before z-scoring; the accounting tells you how to compute those items point-in-time without look-ahead. A signal grounded in the value-driver math (a sustained `ROIC − WACC` spread, a clean FCF yield) is far less likely to be a data-mined ghost than a raw ratio.

**Primary sources:** Koller, Goedhart & Wessels, *Valuation* (McKinsey); Chincarini & Kim, *Quantitative Equity Portfolio Management*; Tortoriello, *Quantitative Strategies for Achieving Alpha*; Gray & Carlisle, *Quantitative Value*; Ilmanen, *Expected Returns*; Grinold & Kahn, *Active Portfolio Management*.

---

## 1. Why fundamentals matter to a quant

A fundamental ratio is just an **alpha factor input**: a transformation of statement/price data that outputs one value per stock per date, designed to predict cross-sectional forward returns (see 04 §1). The three canonical factor families that fundamentals feed are **value** (cheap-on-fundamentals outperforms — B/P, E/P, FCF yield, EV/EBITDA), **quality / profitability** (profitable, low-leverage, high-ROIC firms outperform — ROE, ROIC, gross profitability, accruals), and the **capital-allocation** signals (firms that shrink shares and debt beat issuers). Ilmanen frames value and quality as "alternative betas" — harvestable factor exposures whose premium is *either* rational compensation for a risk others avoid *or* payment for others' systematic mistakes (Ilmanen Ch.5; cross-ref 04 §2). The job of this file is to supply the **valuation logic that disciplines those inputs** and the **accounting that makes them computable point-in-time**.

Two cautions set the frame. First, **always interpret a ratio in industry context and over time, never in isolation** (Chincarini & Kim, ch.4): Tesla's ~1,203 P/E is meaningless against the ~317 auto-industry P/E; J.P. Morgan's ~15 is normal against banks' ~17. This is *why* fundamental factors are almost always **industry-neutralized** before ranking (cross-ref 04 §11). Second, valuation predictors are **poor short-term, strong long-horizon** signals — their simplicity, real-time observability, and lack of hindsight are the advantage, but they can fail when a structural change shifts the long-run mean (Ilmanen Ch.21).

## 2. The value-driver logic (Koller)

The foundation of intrinsic valuation is a single identity: **value is driven by return on invested capital, growth, and the cost of capital** — `Value = f(ROIC, g, WACC)` (Koller, *Valuation*). Two firms with identical growth can be worth very different amounts depending on the *capital they consume to grow*.

**Economic profit (EVA).** The cleanest one-period measure of value creation:
> **Economic profit = Invested Capital × (ROIC − WACC) = NOPAT − (WACC × Invested Capital)** (Koller).

A firm creates value **only when ROIC > WACC**; growth at ROIC = WACC is value-neutral (it just recycles capital at its opportunity cost), and growth at ROIC < WACC **destroys** value. A *sustained* positive `ROIC − WACC` spread is the accounting fingerprint of a durable competitive advantage (a moat), which is exactly why it is a powerful, slow-decaying quality factor (Koller; cross-ref 04 §4).

**The key value driver formula.** For a company growing free cash flow at a constant rate `g`, with NOPAT growing at `g` and reinvesting a fraction of NOPAT to fund that growth, value collapses to:
> **Value = NOPAT₁ × (1 − g/ROIC) / (WACC − g)**, where the **investment rate** `IR = g / ROIC` and **FCF = NOPAT × (1 − g/ROIC)** (Koller).

This formula is the engine behind every fundamental value/quality intuition:
- Higher **ROIC** → smaller reinvestment needed for the same growth → more FCF per unit NOPAT → higher value.
- Higher **growth `g`** raises value **only if ROIC > WACC**; if ROIC ≤ WACC, faster growth lowers value (more capital sunk below cost).
- **The quality×value interaction is not a trade-off.** The math says a high-ROIC, low-growth firm can deserve the *same or higher* multiple as a low-ROIC, high-growth firm — so quality and value must be **combined, not netted** (Koller; e.g. a 23%-ROIC firm vs a 12%-ROIC firm at the same 10× EV/EBITA). This is the theoretical license for the value × quality factor pairing in §6.
- A corollary, **conservation of value:** only things that change cash flows change value. Financial engineering that leaves cash flows untouched — share buybacks' optical EPS lift, accounting-method changes, EPS "accretion" from deals — does **not** create value (Koller). Factors built on those illusions are noise; avoid them.

## 3. Enterprise-DCF mechanics (Koller)

The enterprise-DCF model values the whole operating business by discounting **free cash flow to the firm** at the **WACC**, then bridges to equity. The point for a quant is less the final price than *computing the inputs* — they are the factor building blocks.

**Step 1 — NOPAT (net operating profit after taxes).** Operating profit (EBIT) on an *unlevered* basis, taxed at the operating tax rate: **NOPAT = EBIT × (1 − cash operating tax rate)**, with EBIT taken from *reorganized* statements (strip special/one-off items). Tortoriello's working definition: `NOPAT = operating profit − special items − cash operating taxes`.

**Step 2 — Invested capital.** The capital actually deployed in operations:
> **Invested Capital = operating working capital + net PP&E + net other operating assets** = (equivalently) **total debt + equity − non-operating assets** (Koller).
Reorganize: **exclude excess cash and non-operating assets**, and treat goodwill consistently (with vs without goodwill answers different questions — *with* for value creation to shareholders, *without* for operating performance). Tortoriello's compact version for ratio construction: `Invested Capital = common equity + long-term debt + preferred + minority interest`.

**Step 3 — Free cash flow.** **FCFF = NOPAT + D&A − ΔInvested Capital = NOPAT − net investment** (the cash thrown off after funding reinvestment). For factor work the practical proxy is **FCF = operating cash flow − capex** (Tortoriello) — it sidesteps the reorganization but captures the same economics.

**Step 4 — WACC (the discount rate).**
> **WACC = (E/V)·kₑ + (D/V)·k_d·(1 − tax)**, with the cost of equity from **CAPM: kₑ = r_f + β·ERP** (Koller).
Inputs: a long-maturity risk-free rate; an **equity risk premium ≈ 4–5%** (the long-run U.S. realized excess of stocks over bonds is ~3–5% geometric, but adjusting realized returns for one-off valuation windfalls recovers an *expected* ERP near ~4% — Ilmanen Ch.8); a levered β from the firm's industry. **Caveat from the factor evidence:** Beta is an unreliable risk proxy at the single-stock level — Tortoriello found that **substituting Price-to-Sales for Beta** in the cost-of-capital *consistently improved* economic-profit factor results ("Beta is a poor proxy for risk"; his WACC used r_f 7.5% + β×ERP 9%). Use market weights, not book.

**Step 5 — Continuing (terminal) value.** Most of a DCF's value sits in the post-forecast period. The value-driver continuing value:
> **CV = NOPAT_{T+1} × (1 − g/ROIC_continuing) / (WACC − g)** (Koller),
i.e. the key-driver formula applied to a normalized first post-forecast year. Discipline: the perpetuity `g` must be ≤ long-run nominal GDP, and `ROIC_continuing` should fade toward WACC for firms without a defensible moat (excess returns compete away). Enterprise value = Σ discounted FCFF (explicit horizon) + discounted CV; **equity value = enterprise value − net debt − other non-equity claims**.

## 4. Reading the statements for the right inputs (and red flags)

The factor is only as clean as the line items. Map each fundamental sub-category to its statements (Chincarini & Kim ch.4):
- **Profitability:** examine **GPM / OPM / NPM together and over time** — if OPM rises *more* than GPM, the firm is controlling SG&A well (the Microsoft example). ROE and ROIC sit at the top of the quality stack.
- **Solvency / financial risk:** a high **D/E** is tolerable *only* with strong, stable cash flow and high **interest coverage**; **quick-ratio ≪ current-ratio** means current assets are tied up in inventory (the Walmart example).
- **Cash-flow quality:** **FCF / Operating Income** is the earnings-quality gauge — a low ratio means reported earnings are not converting to cash and are *suspect* (Tortoriello).

**Accounting red flags / the "do-not-buy" facets** (Tortoriello's seven facets include an explicit *red-flags* facet, ch.11):
- **Accruals.** The accrual anomaly — cash-based earnings beat accrual-heavy earnings; **high accruals are a red flag** (the gap between reported earnings and cash flow reverses) (Tortoriello; cross-ref 02). FCF/OI is its practical proxy.
- **External financing / capital allocation.** Firms that **issue shares or debt, or make large cash acquisitions, strongly underperform**; firms that **reduce shares and reduce debt** outperform (Tortoriello §5). This bundles into the **External Financing to Assets** factor (§6) — a premier short.
- **Lag the data.** Financial-statement variables are only known after release: **allow a 2–3 month lag after fiscal-period end**, and pair *beginning-of-month* exposures with the *current-month* return to avoid look-ahead (Chincarini & Kim ch.6; cross-ref 10).

## 5. Relative valuation / multiples and their pitfalls

Multiples are fast, market-anchored shortcuts to the DCF — and most of the strongest value factors are multiples. Key lenses and their failure modes:
- **EV/EBITDA** = (mktcap + total debt − cash)/EBITDA. **Capital-structure-neutral** (uses enterprise value, not just price), which is why it beats P/E for cross-company comparison. Koller prefers **EV/EBITA on forward, normalized earnings**; raw trailing multiples mix in one-offs.
- **E/P (earnings yield), not P/E.** P/E is **undefined/meaningless for negative earnings** — use **E/P** so the factor is monotonic and rankable across the whole universe (Chincarini & Kim ch.6). The smoothed real version, **Shiller CAPE (E10/P)**, tames the cyclicality of 1-year earnings (raw 1-yr E/P drops in bear markets when earnings collapse) (Ilmanen Ch.8). Debate: operating vs reported earnings (operating runs high; forward analyst estimates are over-optimistic).
- **FCF yield (FCF/price)** = (12-mo operating cash flow − capex)/mktcap. The cleanest cash-based value signal — harder to manipulate than earnings.
- **P/B (price-to-book).** Separates **growth (high P/B) from value (low P/B)**, but **book diverges from fair value and says nothing about profitability** — useless alone as a quality signal, yet an excellent *combining* factor (Tortoriello §5; Chincarini & Kim ch.4).
- **Payout yield, not dividend yield.** **Total/net-payout yield** (dividends + buybacks − issuance) is the best carry predictor (~0.42 correlation with annual returns) and beats narrow dividend yield, which failed as a signal through the 1990s; a *too-high* dividend yield foreshadows a cut (Ilmanen Ch.8; Tortoriello §5).
- **PEG / PEGY.** PEG justifies a high P/E by expected growth, PEGY adds dividend yield — but **PEG and plain dividend yield "don't work" as quant factors** (no good quant growth estimate; high yields get cut) (Tortoriello §11; Chincarini & Kim ch.4).
- **General pitfalls:** the **Fed Model** (E/P vs nominal Treasury yield) mixes real and nominal quantities — useful short-term, poor long-term (Asness). And **growth is over-extrapolated**: growth stocks do grow faster early but not enough to justify the valuation gap, so the value story fits the data better (Ilmanen Ch.22).

## 6. Turning fundamentals into tested factors (Tortoriello)

Tortoriello (*Quantitative Strategies for Achieving Alpha*) back-tests single factors and combinations on US equities, reporting the **average annual excess return of the top quintile (Q1) and bottom quintile (Q5)**, the % of rolling periods the factor worked (consistency), and Sharpe. Sign convention: a *good* factor shows a positive, monotonic Q1−Q5 spread. (These results are the empirical spine of the value/quality factors in 04 §4; restated here in the fundamental frame.)

**Day-to-day drivers vs predictors** (Ch.3) — what *moves* stocks is mostly **not** what *predicts* them: EPS growth is the #1 contemporaneous driver (top-quintile +19% vs −11% same-year) **but past EPS growth is not predictive** (~+1%/−1% next year — the market prices it efficiently and growth reverts). **Free-cash-flow growth is "the first predictive basic"** (+2% Q1 / −3% Q5 next-12-mo) — the market is *less* efficient at discounting FCF than EPS. This is the empirical basis for using **cash flow, not earnings, as the forward factor**.

**Valuation — the strongest category (Ch.5), "the sine qua non"; combine liberally:**
- **Free Cash Flow to Price** — the "king of valuation": **Q1 +5.6%, Q5 −4.5%**; 78%/88% consistent; **Sharpe 0.78**; works across sectors and *lacks the post-2003 decay* of other cash factors.
- **EV/EBITDA** — tied for strongest: **Q1 +5.3%, Q5 −4.9%**; very linear; **Sharpe 0.84** (2nd-highest single factor). Best in energy, materials, health care, info tech.
- **P/E** (current-FY estimate) — only **moderate: Q1 +4.7%, Q5 −2.2%**; works in just 4 sectors; further-out estimates worsen the Q5 short ("beware high multiples of future earnings").
- **EV/Sales** — moderate (**Q1 +3.6%, Q5 −4.7%**); usable when there are no earnings.
- **Dividend + Repurchase Yield** — **Q1 +2.4%, Q5 −4.3%**; large-cap, low-vol (**Sharpe 0.75**). Plain dividend yield is weak.
- **P/B** — moderate (**Q1 +3.6%**, Q4/Q5 −2.4%/−1.9%) but an excellent *combiner*.

**Profitability (Ch.4) — strongest when paired with valuation:**
- **ROIC** = NOPAT/(common equity + LT debt + preferred + minority): **Q1 +2.3%, Q5 −4.3%**; strong in bear markets.
- **EBITDA − capex to Invested Capital** — the preferred *simpler* ROIC: **Q1 +2.6%, Q5 −4.5%**.
- **ROE** = (income before extras − pref div)/avg common equity: **Q1 +2.2%, Q5 −3.6%**. **ROA does NOT work for Q1** (assets too broad) but ROE+ROA is a strong *short* (**Q5 −8.3%**).
- **Economic Profits** (crude EVA = ROIC − WACC): progressive refinement basic (Q1 +2.7%/Q5 −0.9%) → **drop Beta** → **substitute P/S for Beta** (Q1 +3.2%/Q5 −3.2%) → **cash-ROIC + P/S-for-Beta is strongest: Q1 +5.1%, Q5 −5.5%, Sharpe 0.87**.

**Cash flow (Ch.6):** **FCF/Operating Income** (earnings quality): Q1 +5.0%/Q5 −3.8%; **Cash ROIC** = FCF/invested capital: Q1 +5.0%/Q5 −5.9%, Sharpe 0.83.

**Capital allocation (Ch.8) — how cash is deployed:** **1-Year Reduction in Shares Outstanding** (cleaner than buyback-cash): **Q1 +3.1%, Q5 −5.2%**; **1-Year Reduction in LT Debt**: Q5 −2.8% (88% consistent); **External Financing to Assets** = net (share+debt issuance − buybacks − debt reduction + Δshort-term debt)/assets: **Q1 +3.1%, Q5 −6.7%**, combines with *every* basic factor. **Acquisitions are a clear negative — avoid acquirers** (bottom-quintile combos −8.8%+).

**The multifactor combination — the central lesson.** Every strong result is a **valuation × quality (or × cash-flow / × capital-allocation) pairing**; value alone and quality alone each leave alpha on the table, but together reach **Sharpe ~0.9–1.0 at just two factors** (Tortoriello). Headline combos:
- **FCF/P + External-Financing-to-Assets → Q5 −15.3%, 100% of 3-yr periods** (strongest short in the book).
- **FCF-per-Share Score + EV/EBITDA → Q1 +8%+, Sharpe 1.03** (highest two-factor result).
- **Economic Profits (cash-ROIC/PS) + EV/EBITDA → Q1 +8.1%, Q5 −6.0%, Sharpe 0.98.**
- **EBIT/Inv.Cap + cash-ROIC + P/S → Sharpe 1.13, Alpha 0.14** — adding a *third* (valuation) factor to a two-factor profitability test lifts Sharpe 0.92 → 1.13.

**Synthesis — the "mosaic" (Ch.11).** Ask three questions on any stock: (1) is the business doing well? (profitability, cash flow, growth); (2) is valuation attractive?; (3) is timing/supply-demand right? (momentum, 52-wk range) — across **seven facets: profitability, valuation, cash flow, growth, capital allocation, price momentum, red flags**. Practical note: **looser thresholds are needed as factors are added**, so Tortoriello prefers **focused 2–3 factor screens over complex ones**; the **Q5 (bottom) quintile is often the cleaner signal** (a better short/avoid list) than Q1 — external-financing, acquisitions, and ROA shorts especially.

## 7. Fundamental factor models & z-score compositing (QEPM)

Chincarini & Kim (*Quantitative Equity Portfolio Management*) give the explicit recipe for turning these statement items into a tradeable score. The **fundamental factor model** treats factor exposures `β` as **directly observable** (the B/P ratio read off the statements) and **estimates the factor premium `f`** by a *pooled cross-sectional / panel regression* of stock returns on exposures each period: `r_{it} = α + β_{it}'·f + ε_{it}` (ch.6). (This is the mirror image of the *economic* factor model, which fixes the premium first and estimates β by time-series regression — cross-ref 04 §5.) Estimation discipline:
- **Universe & window:** ≤ a few thousand stocks (correlation precision degrades with N); **36–60 monthly intervals (3–5 yrs)** balancing precision vs premium stability; monthly rebalancing preferred.
- **Lag to avoid look-ahead** (as in §4): beginning-of-month exposures, 2–3-month lag on statement variables.
- **Estimator robustness:** default **OLS** (`f̂ = (Σβ'β)⁻¹Σβ'r`), but if unstable use the **MAD / minimum-absolute-deviation (median) estimator** — far less outlier-sensitive (in their data **E/P flipped sign OLS→MAD**, exposing outlier-driven estimates) — or keep OLS but report **HAC ("sandwich") standard errors**, which revealed the E/P and B/P premiums were far less precise than naive SEs implied. **Split the sample across time and sectors — premiums should be stable** (tenet 6).
- **Risk decomposition:** total stock risk = **nondiversifiable** `β_i'V(f)β_i` (rewarded) + **diversifiable** `V(ε_i)` (diversified away); in practice set cross-stock specific covariances to zero.

**Z-score compositing (the bridge to ranking).** Standardize each exposure cross-sectionally: `z_{i,k} = (β_{i,k} − mean_k)/S(β_k)` (mean 0, std 1, scale-independent). **Orient every factor so high = good** (use B/P not P/E; multiply detrimental factors by −1) **before** aggregating, then **sum**: `Z_i = (1/K)Σ z_{i,k}` (equal-weight is common for stability; alternatives weight by historical IR or by optimal regression weights). **Winsorize to ±3.** Organize into composites (valuation, profitability, financial-soundness, cash-flow) with intra- and inter-group weights (Chincarini & Kim ch.5; full detail in 04 §5).

## 8. Practical pipeline: point-in-time fundamentals → factor scores → ranking

The end-to-end fundamental-factor pipeline (cross-ref 04 §11 and 10):
1. **Ingest point-in-time fundamentals** — statement items mapped to the security master, **lagged 2–3 months** after fiscal-period end; never use restated/as-of-today values (look-ahead = Type I error: believing a worthless strategy works — cross-ref 10).
2. **Compute the inputs** — NOPAT, invested capital, FCF (= OCF − capex), ROIC, economic profit (ROIC − WACC, P/S-for-Beta), the external-financing aggregate, the multiples (E/P, EV/EBITDA, FCF/P, P/B).
3. **Build raw factors and orient** so high = good; **winsorize**; **z-score cross-sectionally**.
4. **Industry-neutralize** (subtract the cap-weighted industry-average exposure) — industry structure dominates ROIC and uncontrolled value books carry persistent sector bets (Koller; Grinold & Kahn ch.14; Ilmanen Ch.12).
5. **Composite** the z-scores into a value × quality (× cash-flow) blend (§7); the aggregate **Z-score** feeds ad-hoc tilts / stratified selection, the model's **forecast α** feeds mean-variance optimization (cross-ref 04 §11).
6. **Cross-sectionally rank** and form the book — long the top quantile, short/avoid the bottom; **equal-weight the top N** of a strong composite, hold ~12 months, rebalance annually (or buy top-10 quarterly, hold each tranche a year) (Tortoriello ch.13). Mechanical discipline's key virtue is **removing emotion**.
7. **Validate** out-of-sample with proper costs and point-in-time data before sizing (cross-ref 07).

## 9. The *Quantitative Value* algorithm — a turnkey value + quality screen (Gray & Carlisle)

Where §6–§8 treat fundamentals as *individual z-scored factors* to composite, Gray & Carlisle (*Quantitative Value*) give a **complete, sequenced stock-selection system** — a single ranked screen you can run end-to-end. The thesis (ch.2): buy **"a wonderful company at a fair price."** The screen runs a **four-step checklist in order**: (1) **avoid permanent loss** (fraud/manipulation + financial distress); (2) **quality** (economic franchise + financial strength); (3) **price** (the cheapest on EV/EBIT); (4) **confirming signals**; then (5) **assemble & backtest** the combined value+quality model. It is built as a deliberate fix to Greenblatt's **Magic Formula** (rank on ROC + EBIT/TEV): the authors show the Magic Formula is structurally flawed because it **overpays for quality** — it commingles glamour with genuine value ("when you mix raisins and turds, you still have turds" — Munger). Run in the order below, each stage is a *filter or score* applied to the surviving universe. (Every metric here doubles as a directly usable equity factor — cross-ref 04 §4.)

### 9.1 Step 1 — Avoid permanent loss: manipulation, fraud, and distress screens

Eliminate the names most likely to suffer *permanent* (not transient) capital loss **before** any valuation work. Three independent screens, run simultaneously; the universe is cleaned of the worst ~5% on each.

**(a) Earnings manipulation via accruals (ch.3).** Accruals — the wedge where **net income > cash flow** — flag earnings games; low-accrual stocks beat high-accrual stocks (Sloan's accrual anomaly; cross-ref 02, and §4 here where FCF/OI is the same idea). Two complementary measures, combined:
- **STA — scaled total accruals** = `(Net Income − Cash Flow from Operations) / Total Assets` (the real-time form). Sloan's balance-sheet form: `STA = (ΔCA − ΔCash − (ΔCL − Δcurrent-LT-debt − Δtaxes-payable) − Depreciation) / Total Assets`. **Lower is better.** Note its predictive power **decayed after ~1996** (the anomaly got arbitraged).
- **SNOA — scaled net operating assets** = `(Operating Assets − Operating Liabilities) / Total Assets`, where `OA = Total Assets − Cash` and `OL = Total Assets − ST-debt − LT-debt − minority interest − preferred − common equity`. Detects **"bloated balance sheets"** and — unlike STA — **remains a strong predictor of poor long-run returns**.
- **Combine:** `COMBOACCRUAL = average( percentile(STA), percentile(SNOA) )`.

**(b) Beneish PROBM — forensic fraud detection (ch.3).** Eight forensic ratios, each comparing year *t* to *t−1*: **DSRI** (days-sales-in-receivables), **GMI** (gross-margin index), **AQI** (asset-quality index), **SGI** (sales-growth index), **DEPI** (depreciation index), **SGAI** (SG&A index), **LVGI** (leverage index), **TATA** (total accruals to total assets). The score:
> **PROBM = −4.84 + 0.92·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI + 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI**

Convert to a probability: **`PMAN = CDF(PROBM)`** (standard normal, mean 0 / std 1; Excel `NORMDIST`). Track record: caught **12 of 17** notorious fraud cases *before* discovery; flagged stocks earned **9.7%/yr less** (1993–2007); **Enron's PMAN hit 30.5% in 2000**, a full year before collapse.

**(c) Financial distress / bankruptcy probability (ch.4).** Lineage of the models:
- **Altman Z-score** (1968, manufacturing): `Z = 0.012·X1 + 0.014·X2 + 0.033·X3 + 0.006·X4 + 0.999·X5`, with `X1 = WC/TA`, `X2 = Retained Earnings/TA`, `X3 = EBIT/TA`, `X4 = MV equity / BV liabilities`, `X5 = Sales/TA`; **distress cutoff 1.81** (original grey-zone midpoint 2.675). Caught **WorldCom** (Z fell 2.70 → 1.27 → 0.80 over 1999–2001).
- **Ohlson O-score** (1980): a logit model that **fixed the look-ahead bias** in Altman's original estimation.
- **Adopted model — Campbell-Hilscher-Szilagyi PFD** (2008): the authors' choice as **best, with a longer predictive horizon**. The logit:
  > **LPFD = −20.26·NIMTAAVG + 1.42·TLMTA − 7.13·EXRETAVG + 1.41·SIGMA − 0.045·RSIZE − 2.13·CASHMTA + 0.075·MB − 0.058·PRICE − 9.16**, then **`PFD = 1 / (1 + e^(−LPFD))`**.

  Inputs use the **market value of total assets** `MTA = book liabilities + market cap`. `NIMTAAVG` (income) and `EXRETAVG` (excess return) are **4-quarter geometrically-declining weighted averages** with weights **.5333 / .2666 / .1333 / .0666**. Reading the signs: higher **leverage (TLMTA)**, **volatility (SIGMA)**, and **market-to-book (MB)** push toward distress; more **income (NIMTAAVG)**, **cash (CASHMTA)**, **size (RSIZE)**, and **recent return (EXRETAVG)** push toward safety.

**Step-1 execution & payoff.** Simultaneously eliminate the **top 5% of the universe on each** of `COMBOACCRUAL`, `PMAN`, and `PFD`. Cleaning just ~5% of stocks **raised CAGR 10.80% → 11.04%** *and* cut drawdown and volatility — it works by **shifting the return distribution away from the left tail** rather than by adding upside (ch.4, ch.11).

### 9.2 Step 2 — Quality: economic franchise + financial strength

Surviving names are scored for **quality** — *both* a durable economic franchise *and* present-day financial strength. The composite:
> **QUALITY = 0.5·P_FP + 0.5·P_FS**  (equal-weight the percentile of franchise power and the percentile of financial strength).

**(a) Franchise power `P_FP` (ch.5).** Percentile of the **average of four** long-horizon measures. The **8-year horizon** is deliberate: it spans a full business cycle, and because returns mean-revert the screen demands **proven *persistence*, not a one-year spike**. A **geometric** mean is used throughout because it **penalizes volatility** — a real moat throws off *stable* returns:
- **Long-horizon ROA** = 8-yr **geometric** mean of `Net Income before extraordinary items / Total Assets`.
- **Long-horizon ROC** = 8-yr **geometric** mean of `EBIT / Capital` (return on invested capital).
- **Free-cash-flow on assets** `CFOA/FCFA` = `Σ(8-yr free cash flow) / Total Assets`, where `FCF = Net Income + D&A − ΔWorking Capital − capex`.
- **MM — Margin-Max** = `Max( percentile(MG), percentile(MS) )`, where `MG` = 8-yr geometric **gross-margin growth** and `MS` = 8-yr **average gross margin ÷ its standard deviation** (margin *stability*).

This captures Buffett's See's-Candies economics: a **high return on the capital actually required** plus **pricing power** (stable, growing margins). It also subsumes **gross profitability (Novy-Marx): GPA = gross profit / total assets** — the cleanest single quality factor (the numerator sits high on the income statement, above the lines management can dress up), here generalized into the long-horizon margin and FCFA terms.

**(b) Financial strength `P_FS` — the FS_SCORE (ch.6).** A **10-point** score (a modified Piotroski F-Score, scored /10), built from binary tests across three blocks:
- **Profitability (3):** `FS_ROA` (ROA > 0), `FS_FCFTA` (FCF/TA > 0), `FS_ACCRUAL` (FCFTA − ROA > 0, i.e. cash beats accrual earnings).
- **Stability (3):** `FS_LEVER` (LT-debt/TA **fell** YoY), `FS_LIQUID` (current ratio **rose** YoY), `FS_NEQISS` (**net buybacks**: repurchases > issuance).
- **Recent operational improvement (4):** `FS_ΔROA`, `FS_ΔFCFTA`, `FS_ΔMARGIN`, `FS_ΔTURN` (each YoY change > 0 — rising ROA, FCF/TA, gross margin, asset turnover).

**Improvements over Piotroski:** **free cash flow replaces operating cash flow**, and ***net* equity issuance (NEQISS) replaces** Piotroski's simpler "did the firm issue equity?" (EQ_OFFER) test. For reference, **Piotroski's original F-Score (0–9)** — its nine binary components spanning profitability, leverage/liquidity, and operating efficiency — **added ≥ 7.5%/yr to a cheap (low-P/B) portfolio**, concentrated in small/mid caps; the FS_SCORE **edges it out** and is more intuitive.

### 9.3 Step 3 — Price: the value-multiple horse race (EV/EBIT wins)

Among the survivors that are *high quality*, buy the **cheapest**. The authors run a **horse race of value multiples** on equal terms and find a clear winner: **EV/EBIT — "the acquirer's multiple"** — **beat E/P (earnings yield), P/B (book value), FCF yield (free-cash-flow on price), and composite/blended multiples.** EV/EBIT wins because it is **capital-structure- and tax-neutral** (it values the whole enterprise the way a buyer of the *entire business* would, before financing and tax choices) — the same logic that makes EV/EBITDA beat P/E in §5, taken one step further by using EBIT (after maintenance D&A) rather than EBITDA. The price step is therefore a **single, clean ranking on EV/EBIT** (cheapest first), applied *after* quality has already been established — the deliberate inverse of Greenblatt, who lets a high ROC pull glamour-priced names into the portfolio.

### 9.4 Step 4 — Corroboration: confirming signals

Before finalizing, look for **independent confirmation** from informed-money and supply/demand signals (treated as tie-breakers / conviction overlays, not primary filters):
- **Insider and institutional buying** — purchases by executives and 13F institutions corroborate the value thesis.
- **Buybacks** — net share repurchases (consistent with the §6 capital-allocation evidence that share-count *reduction* beats issuance, and with `FS_NEQISS` above).
- **Short interest** — heavy short interest is a **caution flag** against an otherwise-cheap name (the informed-short signal cuts the other way).

### 9.5 Step 5 — Assemble & backtest the combined model

The final model **ranks the loss-screened, high-quality universe on price (EV/EBIT)** and holds the cheapest decile, equal-weighted, rebalanced annually — i.e. **quality + price combined**, the structural opposite of buying cheap-and-hoping. Backtested **~1974–2011**, the combined *Quantitative Value* model **materially outperformed the market and Greenblatt's Magic Formula on both CAGR and risk-adjusted terms** (higher CAGR, higher Sharpe, and positive alpha to the standard factor benchmarks), with the **Step-1 loss screens contributing through lower drawdowns and volatility** rather than raw return — the value+quality pairing delivering what value-alone or the Magic Formula could not. (This is the same lesson as Tortoriello's §6 finding that **valuation × quality** two-factor screens reach Sharpe ≈ 0.9–1.0 where either leg alone falls short — two independent books converging on *combine value and quality, never net them*; validate the magnitudes on your own universe per the checklist below.)

**Why it slots into the factor pipeline.** Every component above is a ready equity factor for §8's machinery: `COMBOACCRUAL`, `PMAN`, `PFD` are *red-flag / do-not-own* factors (oriented so low = good); `P_FP`, `GPA`, and `FS_SCORE` are *quality* factors; `EV/EBIT` is the *value* factor. Drop them into the z-score composite (§7), industry-neutralize (§8 step 4), and the *Quantitative Value* checklist becomes a fully systematic value × quality model (cross-ref 04 §4).

## Cross-references
- **04 — Quant alpha factors & portfolio construction:** the home of the value/quality/profitability factor zoo; the Tortoriello Q1/Q5 table and Koller quality-factor summary live there too (§4); the Gray–Carlisle *Quantitative Value* components (§9) are directly usable factors — `EV/EBIT` (value), `GPA` / `P_FP` / `FS_SCORE` (quality), `COMBOACCRUAL` / `PMAN` / `PFD` (red-flag/do-not-own); the QEPM fundamental-vs-economic model and full z-score compositing recipe (§5); alpha combination, IC/IR evaluation, neutralization, and the alpha→neutralize→optimize→execute pipeline.
- **10 — Data & feature engineering:** point-in-time correctness, the 2–3-month statement lag, look-ahead/survivorship pitfalls, and fundamental-vs-market data refresh cadence that gates what these slow factors can power.
- **02 — Strategies & signals:** Tortoriello's single-factor-backtest → composite-multifactor workflow as a strategy template; the accrual anomaly (STA/SNOA, §9.1) and value/quality/momentum combination; the *Quantitative Value* four-step checklist as a complete screen template.
- **07 — Backtesting & validation:** how to test the Q1/Q5 spreads and composite Sharpe honestly (deflated metrics, OOS, costs, point-in-time data).
- **13 — Behavioral & risk-premia foundations:** Ilmanen's value/carry indicators, the equity risk premium and CAPE, growth over-extrapolation, and the rational-risk-vs-mispricing dichotomy behind why these factors are paid.

## To validate empirically
- **Reproduce the headline spreads** on *your* universe and era: FCF/price (Q1 +5.6%/Q5 −4.5%), EV/EBITDA (Q1 +5.3%/Q5 −4.9%), ROIC, economic-profit (ROIC−WACC), external-financing — and confirm the signs are monotonic and the Sharpes survive costs.
- **Value × quality pairing:** verify the two-factor combos reach **Sharpe ~0.9–1.0** while single factors do not, and that adding a third (valuation) factor lifts Sharpe (≈0.92→1.13) rather than degrading it via threshold loosening.
- **P/S-for-Beta:** test whether substituting Price-to-Sales for CAPM Beta in the economic-profit / WACC construction actually improves the factor on your data ("Beta is a poor proxy for risk").
- **Point-in-time / lag sensitivity:** confirm a 2–3-month statement lag (vs as-reported / restated) materially changes the backtest — quantify the look-ahead inflation if you skip it.
- **Estimator robustness:** re-run the fundamental-factor premium under OLS vs MAD vs HAC SEs and check whether E/P or B/P premiums flip sign or lose significance (the QEPM outlier warning).
- **Conservation-of-value sanity:** confirm buyback-optics / accounting-change signals carry *no* incremental return once cash-flow-based factors are in the composite (they should not, by theory).
- **Quantitative Value — loss screens (§9.1):** compute `COMBOACCRUAL` (STA+SNOA), Beneish `PMAN`, and Campbell-Hilscher-Szilagyi `PFD` on your universe; confirm that **eliminating the worst ~5% on each lowers drawdown/volatility while holding or *raising* CAGR** (their 10.80%→11.04%), i.e. the benefit is left-tail truncation, not added upside. Sanity-check `PMAN` and `PFD` against known frauds/bankruptcies in your data (Enron-, WorldCom-style).
- **EV/EBIT horse race (§9.3):** replicate Gray–Carlisle's value-multiple race on your data and verify **EV/EBIT ("the acquirer's multiple") beats E/P, P/B, FCF yield, and composite multiples** — and that it survives industry-neutralization and costs.
- **Quality combine (§9.2):** test whether `QUALITY = 0.5·P_FP + 0.5·P_FS` (long-horizon ROA/ROC/FCFA + Margin-Max, plus the 10-point FS_SCORE) adds return on top of EV/EBIT, and whether **gross profitability GPA = gross profit/total assets** (Novy-Marx) and the **Piotroski F-Score** independently reproduce their ≥7.5%/yr lift on a low-P/B book (concentrated in small/mid caps).
- **QV vs Magic Formula (§9.5):** backtest the full quality-then-price *Quantitative Value* model against Greenblatt's ROC+EBIT/TEV ranking over a comparable era (~1974–2011) and confirm QV's higher CAGR/Sharpe/alpha — i.e. that ordering quality *before* price (not netting them) avoids "overpaying for quality."
