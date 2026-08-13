# Risk Overlay — Ablation Report

Snapshot `2026-08-11`, code `d6f76139fa1eb7195e020a41cf16cc0aa132df1e`. Pre-registered two-cell diagnostic
(RISK_OVERLAY_ABLATION): overlay-on vs overlay-off on the deployable profile.
Frozen parameters throughout — this report cannot change any shipped value.

> **Correction.** The generated `adv_bind_rate: 1.0` below is a diagnostic artifact:
> `risk_diagnostics` compared the whole book against `adv_cap_w`, so every zero-weight
> name with no ADV data at the date (delisted, or not yet listed) satisfied
> `0 >= 0 - 1e-9` and flagged every rebalance. Recomputed funded-only on the same
> snapshot and code path, the true rate is **0.0** — the ADV cap is inert at $50k,
> exactly the §9 expectation. Every other bind number is unchanged by the fix
> (verified by identical recomputation). The defect is fixed in `risk_diagnostics`;
> the ledger rows carry only summary metrics and are unaffected.

## Headline cost/benefit

| metric | overlay ON | overlay OFF |
|---|---|---|
| cagr | 0.0340 | 0.0903 |
| sharpe | 0.3937 | 0.5512 |
| max_dd | -0.1633 | -0.2776 |
| avg_turnover | 0.1905 | 0.2799 |

## Monkey drawdown

Overlay-on matched-null result: {"profit_pctile": 0.491, "dd_pctile": 0.339, "beats_90": false, "avg_gross_candidate": 0.44517398591128265, "avg_gross_monkeys": 0.5236884467933652}

## Realized vol vs target

Post-k realized vol (rolling 63d, annualized): mean 0.0747, p95 0.1258 against the 0.10 target. The ratchet bounds k, not delivered vol — this path is the overlay's actual output.

## Cap bind rates

`{"n": 1180, "sector_bind_rate_pre2016": 0.01361573373676248, "sector_bind_rate_2016_2018": 0.2037037037037037, "sector_bind_rate_post2018": 0.004866180048661801, "top3_bind_rate": 0.001694915254237288, "top3_without_sector_rate": 0.000847457627118644, "adv_bind_rate": 1.0}`

Sector rates are split at the 2016/2018 GICS boundaries because the sector map
is a declared PIT approximation (risk spec §4.6); pre-2016 rates are measured
against labels the live system would not have had.

ADV no-binds at $50k are expected and are NOT evidence the mechanism works —
the cap is forward-looking fail-closed protection, inert at this equity.

## applied_k path

`{"2008": {"n": 79, "min": 0.2528829150453003, "mean": 0.9157125784332314}, "2020": {"n": 52, "min": 0.264791512155903, "mean": 0.5067524226231832}, "2022": {"n": 52, "min": 0.5613787423135428, "mean": 0.9362351428660413}}`

---

# Interpretation (written by hand, following the calibration-memo convention)

## Verdict against the §9 criteria

**1. Monkey drawdown percentile: 0.001 → 0.339 — better, still failing.** The
overlay reduces the concentration penalty the calibration run measured, but the
candidate's drawdown is still deeper than 66% of matched (overlay-inheriting)
monkeys, so `beats_90` fails its drawdown leg at 0.339 < 0.5. The concentration
mechanism momentum ranking creates is damped, not removed.

**2. The profit percentile collapsed: 1.000 → 0.491.** This is the sharpest result
in the run. Under the shared overlay, random-ranking monkeys run MORE gross than the
candidate (0.524 vs 0.445): a diversified random book has lower ex-ante vol, draws a
smaller k cut, and keeps more exposure. The overlay therefore taxes precisely the
correlated cohort that momentum ranking selects, and on the CAGR axis that tax
consumes the entire measured ranking edge. The ranking still picks winners — the
overlay-off cell and the calibration run prove it — but what survives the vol
target is indistinguishable from a matched null's CAGR.

**3. Realized post-k vol: mean 7.5% vs the 10% target, p95 12.6%.** Over-de-risked
on average, with target overshoot roughly 5% of the time — both directions of the
review's point that the ratchet bounds k, not delivered vol.

**4. Cost/benefit: CAGR 9.03% → 3.40% (−5.63pp), Sharpe 0.551 → 0.394; max DD
−27.8% → −16.3% (+11.4pp), turnover 0.28 → 0.19.** The Sharpe drop shows this is
not clean deleveraging — at a 0% cash rate a constant k preserves Sharpe, so the
loss comes from k's timing. The stress paths say where: the scalar cuts hard and
correctly into 2008/2020/2022 (mins 0.25 / 0.26 / 0.56) but recovers slowly
(2020 mean 0.51 across the whole year — `up_step=0.10` needs ~8 consecutive
up-moves to rebuild from the March floor, and EWMA(63) keeps `k_raw` low well into
the recovery). The overlay buys its drawdown protection mostly by sitting out
recoveries.

**5. Sector binds concentrate inside the 2016–2018 label window: 20.4% vs ~1%
either side.** Exactly where today's GICS map disagrees most with the map that
existed then (between the Real Estate carve-out and the Communication Services
reshuffle). Genuine concentration cannot be separated from label contamination
inside that window without point-in-time GICS — the declared §4.6 follow-up
(Norgate PIT check, owner Viktor). Top-3 binds are negligible (0.17%, and 0.08%
without a simultaneous sector bind).

**6. ADV: corrected bind rate 0.0.** Inert at $50k. Stated per §9: this is not
evidence the mechanism works.

## What this does and does not license

The run is report-only and changes nothing by itself. But its numbers are exactly
the input §5's amendment clause anticipates: the frozen `target_vol=0.10` implies a
roughly half-exposure steady state against this book's natural vol, and
`up_step=0.10` stretches post-crisis re-risking across two-plus months. If that
cost is judged unacceptable, the remedy is a declared constitution amendment
(target_vol and/or up_step) with Viktor's sign-off and a NEW registered diagnostic
run — never an in-place adjustment. The brakes spec (next) takes the overlay-on
book as its input either way; if an amendment is signed first, the brakes
calibration must run on the amended book, not this one.
