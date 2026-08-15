# Floor Fix Diagnostic — Amendment 1 Validation

Snapshot `2026-08-11`, code `ea769d4cbb7cec5b9e3a7e1dcedb2971c8b789fe`. Pre-registered FLOOR_FIX_DIAGNOSTIC: the
AMENDED pipeline (structural $1000 floor). Controls: RISK_OVERLAY_ABLATION
rows (old post-scalar floor). The tv=0.12 cell is research for the live-gate
memo only.

## Cells

| metric | structural floor, tv=0.10 | structural floor, tv=0.12 (research) |
|---|---|---|
| cagr | 0.0443 | 0.0500 |
| sharpe | 0.4756 | 0.4574 |
| max_dd | -0.1530 | -0.1789 |
| avg_turnover | 0.1919 | 0.2216 |
| avg gross | 0.4777 | 0.5553 |

Old-floor controls (ablation, same snapshot lineage): overlay-on CAGR 0.0340,
Sharpe 0.3937, max_dd -0.1633, avg gross 0.4452; monkey profit percentile
0.491, dd percentile 0.339.

## Acceptance cell monkeys (tv=0.10, 1000 matched, overlay-inheriting)

`{"profit_pctile": 0.856, "dd_pctile": 0.514, "beats_90": false, "avg_gross_candidate": 0.47766595038017773, "avg_gross_monkeys": 0.5374218044948409}`

## Realized vol vs target (tv=0.10 cell)

Rolling 63d annualized: mean 0.0836, p95 0.1297 against the 0.10 target.

## Bind rates and applied_k stress paths (tv=0.10 cell)

`{"n": 1180, "sector_bind_rate_pre2016": 0.01361573373676248, "sector_bind_rate_2016_2018": 0.2037037037037037, "sector_bind_rate_post2018": 0.004866180048661801, "top3_bind_rate": 0.001694915254237288, "top3_without_sector_rate": 0.000847457627118644, "adv_bind_rate": 0.0}`

`{"2008": {"n": 79, "min": 0.35645071245234655, "mean": 0.8925828116098036}, "2020": {"n": 52, "min": 0.25951750065343215, "mean": 0.5073864459638011}, "2022": {"n": 52, "min": 0.5618066111235221, "mean": 0.9028781113194315}}`

---

# Interpretation (written by hand, per the calibration-memo convention)

## Verdict against the prereg

**Expected effects: confirmed on all four axes; falsification: none triggered.**

1. **CAGR recovery: +1.03pp of the −2.02pp non-scalar cost** (3.40% → 4.43%).
   Half the unattributed loss was the floor placement alone. The remainder is the
   other non-scalar machinery (entry bars, caps, band retention, approximation
   error of the decomposition) — no evidence the diagnosis was wrong, and no basis
   to chase the rest.
2. **Monkey profit percentile 0.491 → 0.856** — the amendment's core claim, and the
   clearest confirmation: the old floor was a hidden tax on ranking skill. The
   drawdown leg now PASSES (0.339 → 0.514). `beats_90` overall remains false by the
   profit leg alone (0.856 < 0.90) — a near miss of the panel's strict criterion.
   The residual gap is consistent with the overlay's remaining differential k-tax
   on concentrated books (structural: a concentrated book draws lower k than a
   diversified null; gross gap narrowed 0.079 → 0.060 but persists). This gate on
   the overlay-on book is diagnostic; the deployment gate remains the full
   production-profile gauntlet re-run.
3. **Gross 0.445 → 0.478**, toward but not at the ~0.55 arithmetic bound — the
   structural floor still (correctly, by design) skips sub-$1000 structural
   signals, and entry bars still bind.
4. **maxDD −15.3%**, inside §8's 15–25% expectation band — and the fix *improved*
   drawdown vs the old floor (−16.3%): the deleted names were not protective.

Also confirming the modeled-vs-delivered vol argument (panel round 1): delivered
vol mean rose 7.5% → 8.4% against the 10% target, and 2008's k floor rose
0.253 → 0.356 — sigma_p now prices the book actually held.

## The tv=0.12 research cell (live-gate memo input; decides nothing now)

CAGR 5.00% (+0.57pp vs tv 0.10), maxDD −17.9% (−2.6pp), avg gross 0.555 — but
**Sharpe 0.457 vs 0.476: LOWER**. The counterfactual grid predicted roughly flat
Sharpe; the real pipeline disagrees. On this sample the extra exposure buys return
but not risk-adjusted return. The 6-month gate memo should weigh this against live
efficiency data; on today's evidence the case for 0.12 is weaker than the grid
suggested — the panel's round-2 caution (approximate, in-sample, ignores pipeline
interactions) was correct in direction and sign.

## Status

Amendment 1 (structural floor + structural beta) stands validated. The overlay-on
book for the brakes spec is the tv=0.10 structural-floor cell of this run.
