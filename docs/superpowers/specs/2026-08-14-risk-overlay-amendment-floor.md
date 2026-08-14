# Risk Overlay Amendment 1 — structural floor, structural beta, target_vol deferred

**Status:** adopted 2026-08-14 on Viktor's standing instruction ("discuss with other
LLMs via manifold; on consensus, move forward"), after a 2-round cross-model panel
(manifold consultations; round 1: 4/6 answered, unanimous on the substance; round 2 on
the §8 sequencing clause: 6/6 answered, 5–1). Inputs:
`docs/research/2026-08-risk-overlay-ablation.md` (registered RISK_OVERLAY_ABLATION) and
`docs/research/2026-08-overlay-amendment-analysis.md`.

## 1. What changes

### 1.1 Position floor is structural (defect correction, NOT a preference change)

Blueprint §8's own text defines the $1000 floor as signal-level: "below ⇒ skip
signal — frictions eat it." The implementation applied it to POST-scalar funded
weights, so at low k the floor silently deleted ATR-parity names (~0.10 of average
gross in the ablation; the dominant share of the −2.02pp non-scalar CAGR cost and a
mechanical driver of the monkey profit-percentile collapse 1.000 → 0.491). The scalar's
contract is scale, not selection; the covariance model priced a book that was not the
one delivered.

Amended pipeline (risk path only; `risk=None` byte-identical as before): drift band →
**floor on structural weights** → vol scalar → validate. Funded positions may sit
under $1000 by the factor k; a minimum ORDER size is an order-service concern and may
be specified there. Recorded explicitly as a correction of implementation drift
against written intent — its measured gain is never evidence for a strategy claim and
does not pass through the DSR machinery.

### 1.2 Beta band watches structural beta

Funded beta ≈ k × structural beta, so under a binding scalar the funded book sits low
in the band by construction: the recorded series shows out-of-band 24.9% of
rebalances, streaks of 40, and 23 would-be pages — the monitor was tracking k, not
selection drift. `risk_diagnostics` now records `beta_structural = beta / applied_k`
alongside the funded `beta`; the band (0.3–0.8) and `beta_breach_n=4` are UNCHANGED
and evaluate `beta_structural`. Page frequency is re-measured on the amended book
before any threshold change (prospective calibration, not fitted to this history).

### 1.3 target_vol: NOT raised. Deferred to the written gate

The ablation showed `target_vol=0.10` binds on 87.6% of rebalances (median sigma_p
14.2%) — a standing ~30% exposure cut, and the panel's round-1 consensus favored
0.12 (the KB-08 futures-fund norm; explicitly not 0.14, which equals the in-sample
median sigma_p). Blueprint §8 however reads: "Raise only after 6 months of live
efficiency in band." Round 2 of the panel voted 5–1 to respect the clause:

- A purposive carve-out ("the clause targets greed, not structural corrections") on
  the clause's first contact with a real decision would zero its binding force —
  every future raise can be narrated as structural.
- Independent engineering reason: the floor fix (§1.1) itself changes vol delivery.
  Raising the setpoint in the same release would confound attribution of the first
  live realized-vol series, and raising a setpoint to compensate for a delivery leak
  is the wrong remedy class.
- Cost of compliance is small: roughly $100–250 over the six months at $50k.

Therefore: `target_vol` stays 0.10. The 0.12 question is decided at the 6-month live
gate by a human-signed decision memo (auto-activation rejected: "raise only after" ≠
"raise automatically after"; the gate is necessary, not sufficient). Before go-live
the gate must be defined mechanically: efficiency statistic, band, measurement window,
minimum observations, and treatment of halted/partial periods.

### 1.4 Not amended

`up_step=0.10` and the ratchet (−0.29pp, binds 6.5% of rebalances — the declared
anti-procyclicality premium), covariance parameters, all caps, spread gate.

## 2. Validation

New pre-registered diagnostic FLOOR_FIX_DIAGNOSTIC (DIAGNOSTIC_FAMILY, report-only):

- Cell 1: amended pipeline, `target_vol=0.10` — with 1000 matched monkeys.
- Cell 2: amended pipeline, `target_vol=0.12` — cell only, RESEARCH input for the
  future gate memo; running it is not authorization to deploy it.
- Controls: the RISK_OVERLAY_ABLATION ledger rows (old floor, tv 0.10, same snapshot
  lineage) and the analytic constant-k row in the amendment analysis.

Acceptance criterion (panel round 1): material recovery of the matched-monkey profit
percentile on cell 1 — not a CAGR level. Drawdown must stay inside §8's declared
15–25% expectation band.

## 3. Bookkeeping

- Blueprint §8 text change required on sign-off: floor line gains "(structural
  weights, pre-scalar — amendment 2026-08-14)"; beta-band line gains "(structural
  beta)". The two OLDER §11 amendments from the 2026-08-06 spec (stage order,
  estimator) remain separately pending Viktor's sign-off.
- Code: `strategies/sizing.py::resolve_book` (floor moved, steps renumbered),
  `risk/overlay.py::risk_diagnostics` (`beta_structural`). Tests pin both contracts.
