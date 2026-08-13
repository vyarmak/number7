# Overlay Amendment Analysis — decision support for the §5 constants

**Inputs:** the two registered RISK_OVERLAY_ABLATION cells (snapshot `2026-08-11`),
re-executed deterministically; all analytics are arithmetic on their recorded series
(`applied_k`, `k_raw`, `sigma_p`, `beta` per rebalance, plus the overlay-off daily
return stream). **No new registered runs, nothing logged to the ledger.**

**Method caveats, read first.** Counterfactual k paths are replayed from the recorded
`sigma_p` series (approximately k-independent) and applied to the overlay-off daily
returns with weekly forward-fill. This ignores cap/band/floor interaction with k, and
it is in-sample by construction — it bounds what a constant could have delivered on
this history; it forecasts nothing. Sharpe here is simple-return mean/std·√252, which
runs ~0.08 higher than `summary()`'s log-return Sharpe — compare counterfactual rows
only against the "recorded k × off returns" row computed the same way, never against
the actual cells directly. Any amendment chosen from this table still requires its own
registered diagnostic run on the real pipeline.

## 1. The scalar is a permanent haircut, not a crisis brake

| statistic | value |
|---|---|
| median ex-ante book vol (`sigma_p`) | **14.2%** (p90 24.7%) |
| rebalances with `applied_k < 1` | **87.6%** |
| mean / median `applied_k` | 0.696 / 0.697 |
| rebalances where the ratchet binds (`k_raw > applied_k`) | **6.5%** (mean gap 0.123) |

At `target_vol=0.10` against a book whose *median* ex-ante vol is 14.2%, the scalar is
on almost nine rebalances out of ten. The vol target functions as a ~30% standing
exposure cut with occasional deep crisis cuts — not as an episodic brake.

## 2. Where the −5.63pp CAGR actually went

Waterfall on the approximation methodology (off-cell daily returns, CAGRs real):

| step | CAGR | Δ |
|---|---|---|
| overlay OFF (actual) | 9.03% | — |
| × constant k = 0.696 (level effect) | 6.48% | **−2.55pp** |
| × perfect-foresight `k_raw` (adds k_raw timing) | 5.70% | −0.78pp |
| × recorded `applied_k` (adds ratchet lag) | 5.42% | **−0.29pp** |
| actual overlay ON | 3.40% | **−2.02pp unexplained by the scalar** |

Three conclusions:

- **The ratchet is nearly free (−0.29pp).** It binds 6.5% of the time. `up_step` is
  NOT the expensive parameter; the counterfactual grid confirms (below). My earlier
  read blaming 2020's slow recovery on `up_step` was wrong — `k_raw` itself stayed low
  because EWMA(63) vol stayed elevated; the ratchet added almost nothing on top.
- **The level effect dominates the scalar's cost (−2.55pp)** — a direct consequence of
  `target_vol=0.10` vs the book's 14.2% median vol.
- **−2.02pp comes from the overlay machinery that is NOT the scalar** — see §3.

## 3. The unattributed −2.02pp: the floor × k interaction

`min_position_dollars=1000` is applied AFTER the scalar (spec §6 step 9, deliberate:
sub-$1000 positions are uneconomic). At $50k sleeve equity the floor is 2% of book; at
`applied_k ≈ 0.63` a position must exceed **~3.2% structural weight to survive**, and
ATR-parity positions run 2–4%. The floor therefore silently deletes a large fraction of
the book exactly when k is low: measured average gross is **0.445** against
`mean_k × off-gross ≈ 0.70 × 0.78 ≈ 0.55` — roughly **0.10 of gross lost**, plus
entry bars and cap shaving. This also feeds the monkey profit-percentile collapse:
the candidate's concentrated book draws lower k than diversified monkeys, so it loses
MORE names to the floor — a second, hidden tax on ranking skill. Confirming the exact
floor share needs one instrumented diagnostic cell (a registration decision, not made
here).

## 4. Counterfactual (target_vol, up_step) grid

Same methodology as §2 (compare against the 5.42% row, not against actual ON).
maxDD here is on the scaled off-stream; the real pipeline's DD would differ.

| tv \ up_step | 0.10 | 0.25 | 1.00 (no ratchet) | mean k @0.10 | maxDD @0.10 |
|---|---|---|---|---|---|
| **0.10** (current) | 5.42% | 5.53% | 5.66% | 0.73 | −17.7% |
| **0.12** | 6.12% | 6.19% | 6.28% | 0.82 | −20.1% |
| **0.14** | 6.82% | 6.85% | 6.88% | 0.88 | −21.9% |
| **0.16** | 7.21% | 7.21% | 7.22% | 0.92 | −23.5% |

Reading: each +0.02 of `target_vol` buys ~0.7pp of CAGR and costs ~2pp of drawdown
(off reference: 9.03% / −27.8%). `up_step` moves the needle ≤0.24pp anywhere in the
grid — amending it alone is not worth a constitution change. Note tv=0.14 ≈ the
median `sigma_p`: at that setting the scalar becomes a true tail brake (k<1 roughly
half the time instead of 88%). The floor tax of §3 also shrinks as k rises, so real
pipeline results at higher tv should land somewhat ABOVE these rows — direction, not
promise.

## 5. Beta band monitor would have paged 23 times

Recorded beta (monitor-only): mean 0.53, out-of-band **24.9%** of rebalances, longest
streak **40 consecutive rebalances** (~10 months), and the `beta_breach_n=4` page rule
fires **23 times** over the sample. As calibrated, the pager is a nuisance alarm.
Worth folding into the same amendment discussion (band width or breach_n), since it is
also a frozen §5 constant.

## 6. What this licenses

Nothing, by itself. It says: if the ablation's cost is unacceptable, the effective
levers in order are (1) `target_vol`, (2) the floor's interaction with k (design
question: floor before vs after scalar, or floor on structural weights), (3) beta-band
monitor calibration. `up_step` is not worth amending on this evidence. Any chosen
amendment is a declared §11-style constitution change with Viktor's sign-off and a NEW
registered diagnostic run on the amended pipeline; the brakes spec then calibrates on
that book.
