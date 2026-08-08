from __future__ import annotations

from number7.research.registry import PreRegistration

CANDIDATE_FAMILY = "clenow_momentum"
DIAGNOSTIC_FAMILY = "clenow_diagnostic"

_CITATIONS = ["KB-02 Clenow, Stocks on the Move",
              "KB-08 Clenow, Trading Evolved",
              "KB-11 §9a", "blueprint §6", "spec 2026-07-23-clenow-momentum-sleeve-design"]

_MECHANISM = (
    "Cross-sectional equity momentum: over a 90-session window the OLS slope of log price "
    "against ordinal session index, annualized at 250 sessions and multiplied by R-squared "
    "as a smoothness penalty, ranks S&P 500 constituents. Positions are ATR-parity sized "
    "so each name targets the same daily dollar move, and a 200-day SMA regime gate on the "
    "index proxy blocks NEW entries while leaving retained names funded and re-sized. "
    "The economic claim is 12-month-scale price continuity net of noise; the R-squared "
    "term is a smoothness heuristic, not a significance test.")

CLENOW_REFERENCE = PreRegistration(
    family=CANDIDATE_FAMILY,
    origin="human",
    mechanism=_MECHANISM + (" REFERENCE PROFILE: the published parameters exactly, with "
                            "production overlays off. This is FIDELITY EVIDENCE, not an "
                            "alpha claim, and is never treated as deployable evidence."),
    citations=_CITATIONS,
    expected_effect=(
        "Reproduces the published system's qualitative behaviour on the 2005-2014 overlap: "
        "positive Sharpe, drawdown materially shallower than a fully-invested index through "
        "2008, and average gross exposure well below 1.0. A correct implementation may still "
        "underperform the book - window choice, cash treatment, fees, vendor differences and "
        "post-publication decay are all legitimate causes."),
    falsification=(
        "Regime-off episodes do not precede index drawdowns more often than chance across "
        "2004-present; or the paired regime-gate ablation shows no exposure-adjusted "
        "improvement; or the full system fails to beat its own no-R2 / no-gap / equal-weight "
        "ablations; or DSR falls below the 0.98 hurdle. Any of these is a documented KILL."),
    param_space={"lookback": [90], "atr_window": [20], "ma_filter": [100],
                 "regime_ma": [200], "gap_threshold": [0.15], "risk_factor": [0.001],
                 "hold_top_pct": [0.20], "max_positions": [30], "drift_band": [0.05]},
)

CLENOW_SEARCHED = PreRegistration(
    family=CANDIDATE_FAMILY,
    origin="human",
    mechanism=_MECHANISM + (" SEARCHED VARIANT: the declared neighbourhood of the published "
                            "parameters. Registered separately from the reference point "
                            "because a one-point replication has no search, so DSR is not "
                            "meaningfully applicable at N=1."),
    citations=_CITATIONS,
    expected_effect=(
        "Performance is a smooth, broad plateau in the parameter neighbourhood rather than a "
        "spike at the published point. A sharp optimum would itself be evidence of fitting."),
    falsification=(
        "The published point is a lone spike surrounded by materially worse neighbours; or "
        "the best cell fails the 0.98 DSR hurdle once the full declared space is counted; or "
        "walk-forward efficiency falls below the 0.5 floor."),
    param_space={"lookback": [60, 90, 120], "atr_window": [14, 20], "ma_filter": [100],
                 "regime_ma": [200], "gap_threshold": [0.15], "risk_factor": [0.001],
                 "hold_top_pct": [0.20], "max_positions": [20, 30], "drift_band": [0.05]},
)

RISK_OVERLAY_ABLATION = PreRegistration(
    family=DIAGNOSTIC_FAMILY,
    origin="human",
    mechanism=(
        "Risk-layer overlay ablation (risk spec §9): the deployable Clenow profile run "
        "with and without the portfolio risk overlay (vol-target scalar with ratchet, "
        "sector/top-3 caps, ADV cap, spread gate). Every overlay parameter is a frozen "
        "constitution constant declared a priori - zero searched dimensions. The run "
        "measures the overlay's cost/benefit; it cannot change any shipped value."),
    citations=["KB-08 Clenow, Trading Evolved", "blueprint §8",
               "spec 2026-08-06-portfolio-risk-layer-design",
               "docs/research/2026-08-clenow-calibration-memo.md (monkey drawdown)"],
    expected_effect=(
        "Overlay-on: realized vol nearer the 10% target, monkey drawdown percentile "
        "materially above 0.001, moderate CAGR/Sharpe cost. Sector-cap binds reported "
        "split at the 2016/2018 GICS boundaries because the historical sector map is a "
        "declared PIT approximation."),
    falsification=(
        "Overlay-on drawdown is NOT improved versus overlay-off; or the realized-vol "
        "path ignores the target (scalar inert); or the overlay costs more Sharpe than "
        "the drawdown improvement justifies under §8's stated risk preferences. Any of "
        "these triggers a declared amendment review, never a parameter search."),
    param_space={"overlay": ["on", "off"]},
)

CLENOW_DIAGNOSTIC = PreRegistration(
    family=DIAGNOSTIC_FAMILY,
    origin="human",
    mechanism=_MECHANISM + (" DIAGNOSTICS ONLY: ablations, the reference/deployable profile "
                            "pair, cash-rate and cost-sensitivity runs. None is a deployment "
                            "candidate, so none counts toward the DSR trial budget - which is "
                            "why they live in a separate ledger family (spec §10)."),
    citations=_CITATIONS,
    expected_effect=("Each ablation degrades the full system: removing R-squared, the regime "
                     "gate, the gap filter, or ATR parity should each cost exposure-adjusted "
                     "return. If the full system cannot beat its own ablations the "
                     "implementation is suspect; if it crushes them, that is also signal."),
    falsification=("An ablation matches or beats the full system, indicating a component is "
                   "inert or actively harmful as implemented."),
    param_space={"ablation": ["none", "no_r2", "no_regime", "no_gap", "equal_weight"],
                 "cost_multiple": [0.0, 1.0, 2.0],
                 "cash_annual_rate": [0.0, 0.02, 0.04],
                 "profile": ["reference", "deployable"]},
)
