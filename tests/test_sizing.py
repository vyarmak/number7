import numpy as np
import pandas as pd
import pytest

from number7.engine.strategy import Slate
from number7.risk.overlay import RiskConfig, RiskContext
from number7.strategies.sizing import (SizingConfig, apply_drift_band, apply_sector_cap,
                                       apply_top3_cap, holdings_from_shares,
                                       resolve_book, validate_book)

SYMS = ["A", "B", "C", "D"]


def _slate(weights: dict, admit_new: bool = True) -> Slate:
    w = pd.Series(0.0, index=SYMS)
    w.update(pd.Series(weights))
    funded = w[w > 0]
    rank = pd.Series(np.nan, index=SYMS, dtype=float)
    rank[funded.index] = np.arange(1.0, len(funded) + 1.0)   # dict order = rank order
    return Slate(weights=w, rank=rank, admit_new=admit_new)


def _cfg(**kw) -> SizingConfig:
    return SizingConfig(sleeve_equity=50_000.0, **kw)


def _flat() -> pd.Series:
    return pd.Series(0.0, index=SYMS)


def test_budgeted_fill_skips_the_marginal_name_and_stops():
    slate = _slate({"A": 0.5, "B": 0.4, "C": 0.3, "D": 0.05})
    book = resolve_book(slate, _flat(), _cfg(position_cap=1.0))
    assert book["A"] == pytest.approx(0.5) and book["B"] == pytest.approx(0.4)
    assert book["C"] == 0.0 and book["D"] == 0.0     # C does not fit; the walk terminates


def test_max_positions_truncates_the_fill():
    slate = _slate({"A": 0.1, "B": 0.1, "C": 0.1, "D": 0.1})
    book = resolve_book(slate, _flat(), _cfg(max_positions=2))
    assert int((book > 0).sum()) == 2 and book["A"] > 0 and book["B"] > 0


def test_position_cap_clips_and_can_strand_budget():
    """Spec §8.2 orders fill (2) BEFORE cap (3): the 0.40 name consumes 0.40 of budget
    and is then clipped to 0.10. The stranded 0.30 is expected, not a bug."""
    slate = _slate({"A": 0.4, "B": 0.4, "C": 0.4})
    book = resolve_book(slate, _flat(), _cfg())
    assert book["A"] == pytest.approx(0.10) and book["B"] == pytest.approx(0.10)
    assert book["C"] == 0.0
    assert book.sum() == pytest.approx(0.20)


def test_gross_normalization_scales_down_proportionally():
    slate = _slate({"A": 0.6, "B": 0.4})
    book = resolve_book(slate, _flat(), _cfg(position_cap=1.0, gross_max=0.5))
    assert book.sum() == pytest.approx(0.5)
    assert book["A"] / book["B"] == pytest.approx(1.5)


def test_floor_is_applied_after_normalization():
    """A $1,050 position pushed below $1,000 by normalization must be dropped (§8.2.5)."""
    slate = _slate({"A": 0.9, "B": 0.021})
    cfg = _cfg(position_cap=1.0, gross_max=0.5, min_position_dollars=1000.0)
    book = resolve_book(slate, _flat(), cfg)
    assert book["B"] == 0.0
    assert book["A"] > 0


def test_regime_off_restricts_candidates_to_still_eligible_holdings():
    slate = _slate({"A": 0.2, "B": 0.2}, admit_new=False)
    current = pd.Series({"A": 0.0, "B": 0.15, "C": 0.10, "D": 0.0})
    book = resolve_book(slate, current, _cfg(position_cap=1.0))
    assert book["B"] == pytest.approx(0.2)       # held AND still eligible -> re-sized UP
    assert book["A"] == 0.0                      # eligible but not held -> not admitted
    assert book["C"] == 0.0                      # held but no longer eligible -> exited


def test_drift_band_holds_inside_and_trades_outside():
    cfg = _cfg(drift_band=0.05)
    target = pd.Series({"A": 0.10, "B": 0.10, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.097, "B": 0.093, "C": 0.0, "D": 0.0})   # -3% / -7%
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == pytest.approx(0.097)      # inside band -> keep current, no order
    assert out["B"] == pytest.approx(0.10)       # outside band -> trade to target


def test_entries_and_exits_always_execute():
    cfg = _cfg(drift_band=0.99)
    target = pd.Series({"A": 0.10, "B": 0.0, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.0, "B": 0.10, "C": 0.0, "D": 0.0})
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == pytest.approx(0.10) and out["B"] == 0.0


def test_retention_that_would_breach_position_cap_forces_the_trade():
    """The exact silent-breach case in spec §8.3: clipped to 0.10, current 0.104,
    |delta|/target = 4% <= 5% band -> would be kept at 0.104 and never caught, because
    validate_weights does not check position_cap."""
    cfg = _cfg(position_cap=0.10, drift_band=0.05)
    target = pd.Series({"A": 0.10, "B": 0.0, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.104, "B": 0.0, "C": 0.0, "D": 0.0})
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == pytest.approx(0.10)
    validate_book(out, cfg)                       # must not raise


def test_retention_that_would_breach_gross_max_forces_trades():
    cfg = _cfg(position_cap=1.0, gross_max=1.0, drift_band=0.05)
    target = pd.Series({"A": 0.25, "B": 0.25, "C": 0.25, "D": 0.25})
    current = pd.Series({"A": 0.26, "B": 0.26, "C": 0.26, "D": 0.26})   # +4% each
    out = apply_drift_band(target, current, cfg)
    assert out.sum() <= 1.0 + 1e-9
    validate_book(out, cfg)


def test_forced_resize_after_n_stale_periods():
    cfg = _cfg(drift_band=0.05, forced_resize_periods=3)
    target = pd.Series({"A": 0.10, "B": 0.10, "C": 0.0, "D": 0.0})
    current = pd.Series({"A": 0.098, "B": 0.098, "C": 0.0, "D": 0.0})
    stale = pd.Series({"A": 3, "B": 0, "C": 0, "D": 0})
    out = apply_drift_band(target, current, cfg, stale)
    assert out["A"] == pytest.approx(0.10)       # stale -> forced re-size
    assert out["B"] == pytest.approx(0.098)      # fresh -> held


def test_validate_book_rejects_cap_and_gross_breaches():
    cfg = _cfg()
    with pytest.raises(ValueError, match="position_cap"):
        validate_book(pd.Series({"A": 0.2}), cfg)
    with pytest.raises(ValueError, match="gross_max"):
        validate_book(pd.Series({"A": 0.1, "B": 0.1}), _cfg(gross_max=0.15))


def test_resolved_book_always_passes_its_own_validator():
    """Property test over random slates: no path through resolve_book may emit a book
    that breaches the contract (spec §12 contract-wide)."""
    rng = np.random.default_rng(0)
    cfg = _cfg()
    for _ in range(200):
        w = pd.Series(rng.uniform(0.0, 0.35, len(SYMS)), index=SYMS)
        rank = pd.Series(rng.permutation(np.arange(1.0, len(SYMS) + 1.0)), index=SYMS)
        slate = Slate(weights=w, rank=rank, admit_new=bool(rng.integers(2)))
        current = pd.Series(rng.uniform(0.0, 0.2, len(SYMS)), index=SYMS)
        validate_book(resolve_book(slate, current, cfg), cfg)


def test_holdings_come_from_shares_and_the_signal_date_close():
    """Spec §8.4: never broker market value - the live path runs on the morning of T and
    must mark at T-1's official close, exactly as the backtest does."""
    raw = pd.Series({"A": 100.0, "B": 50.0, "C": 10.0, "D": 1.0})
    out = holdings_from_shares({"A": 25, "B": 40}, raw, sleeve_equity=50_000.0)
    assert out["A"] == pytest.approx(0.05) and out["B"] == pytest.approx(0.04)
    assert out["C"] == 0.0


# ---------------------------------------------------------------- risk overlay caps

def _rc(sector: dict, adv: dict | None = None, cols=None, k_prev=1.0, cfg=None):
    cols = cols if cols is not None else list(sector)
    return RiskContext(
        sigma=pd.DataFrame(np.eye(len(cols)) * 0.04, index=cols, columns=cols),
        corr=pd.DataFrame(np.eye(len(cols)), index=cols, columns=cols),
        adv_cap_w=pd.Series(adv if adv else 1.0, index=cols, dtype=float),
        entry_barred=frozenset(),
        sector=pd.Series(sector).reindex(cols).fillna("UNKNOWN"),
        assetid=pd.Series(np.arange(1.0, len(cols) + 1.0), index=cols),
        k_prev=k_prev, config=cfg if cfg is not None else RiskConfig(),
    )


# a 2-3 name test book legitimately breaches the 25% top-3 cap; these fixtures loosen
# the concentration caps so the SCALAR path is what the test exercises
_LOOSE = RiskConfig(top3_cap=1.0, sector_cap=1.0)


def test_sector_cap_scales_breaching_sector_proportionally_shortfall_to_cash():
    w = pd.Series({"A": 0.20, "B": 0.10, "C": 0.15})
    sector = pd.Series({"A": "Tech", "B": "Tech", "C": "Energy"})
    out = apply_sector_cap(w, sector, cap=0.25)
    assert out["A"] == pytest.approx(0.20 * 0.25 / 0.30)
    assert out["B"] == pytest.approx(0.10 * 0.25 / 0.30)
    assert out["C"] == 0.15                     # untouched sector
    assert out.sum() < w.sum()                  # shortfall to cash, not redistributed


def test_sector_cap_applies_to_unknown_bucket():
    w = pd.Series({"A": 0.20, "B": 0.20})
    sector = pd.Series({"A": "UNKNOWN", "B": "UNKNOWN"})
    assert apply_sector_cap(w, sector, cap=0.25).sum() == pytest.approx(0.25)


def test_top3_cap_scales_three_largest_to_fit():
    w = pd.Series({"A": 0.12, "B": 0.11, "C": 0.10, "D": 0.02})
    out = apply_top3_cap(w, cap=0.25, assetid=pd.Series({"A": 1.0, "B": 2.0,
                                                         "C": 3.0, "D": 4.0}),
                         max_iter=30)
    top3 = out.nlargest(3).sum()
    assert top3 == pytest.approx(0.25, abs=1e-9)
    assert out["D"] == 0.02


def test_top3_cap_fixed_point_when_fourth_name_promotes():
    # scaling the top 3 drops them below D -> D enters the top 3 -> second pass needed
    w = pd.Series({"A": 0.30, "B": 0.30, "C": 0.30, "D": 0.089})
    out = apply_top3_cap(w, cap=0.25, assetid=pd.Series({"A": 1.0, "B": 2.0,
                                                         "C": 3.0, "D": 4.0}),
                         max_iter=30)
    assert out.nlargest(3).sum() <= 0.25 + 1e-9


def test_top3_cap_raises_after_max_iter():
    w = pd.Series({"A": 0.30, "B": 0.30, "C": 0.30, "D": 0.089})
    with pytest.raises(RuntimeError, match="top-3"):
        apply_top3_cap(w, cap=0.25, assetid=pd.Series({"A": 1.0, "B": 2.0,
                                                       "C": 3.0, "D": 4.0}), max_iter=1)


def test_validate_book_with_risk_checks_sector_top3_adv():
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30)
    risk = _rc({"A": "Tech", "B": "Tech", "C": "Tech"})
    bad_sector = pd.Series({"A": 0.10, "B": 0.10, "C": 0.10})
    with pytest.raises(ValueError, match="sector"):
        validate_book(bad_sector, cfg, risk=risk)
    risk2 = _rc({"A": "T1", "B": "T2", "C": "T3"})
    with pytest.raises(ValueError, match="top-3"):
        validate_book(pd.Series({"A": 0.10, "B": 0.10, "C": 0.10}), cfg, risk=risk2)
    risk3 = _rc({"A": "T1", "B": "T2", "C": "T3"}, adv={"A": 0.05, "B": 1.0, "C": 1.0})
    with pytest.raises(ValueError, match="adv"):
        validate_book(pd.Series({"A": 0.10, "B": 0.05, "C": 0.05}), cfg, risk=risk3)


def test_validate_book_without_risk_unchanged():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.10)
    w = pd.Series({"A": 0.10, "B": 0.10, "C": 0.05})
    assert validate_book(w, cfg) is w


def test_band_retention_breaching_sector_cap_is_forced_to_target():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, drift_band=0.10)
    risk = _rc({"A": "Tech", "B": "Tech", "C": "Energy"})
    target = pd.Series({"A": 0.125, "B": 0.125, "C": 0.10})   # Tech = 0.25, at cap
    current = pd.Series({"A": 0.13, "B": 0.13, "C": 0.10})    # retention -> 0.26 breach
    out = apply_drift_band(target, current, cfg, risk=risk)
    assert out.groupby(risk.sector.reindex(out.index)).sum()["Tech"] <= 0.25 + 1e-9


def test_band_retention_breaching_adv_cap_is_forced_to_target():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, drift_band=0.10)
    risk = _rc({"A": "T1", "B": "T2", "C": "T3"}, adv={"A": 0.12, "B": 1.0, "C": 1.0})
    target = pd.Series({"A": 0.115, "B": 0.10, "C": 0.10})
    current = pd.Series({"A": 0.125, "B": 0.10, "C": 0.10})   # in band, above ADV cap
    out = apply_drift_band(target, current, cfg, risk=risk)
    assert out["A"] == pytest.approx(0.115)


def test_band_retention_breaching_top3_cap_is_forced_to_target():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, drift_band=0.10)
    risk = _rc({"A": "T1", "B": "T2", "C": "T3", "D": "T4"})
    target = pd.Series({"A": 0.085, "B": 0.085, "C": 0.08, "D": 0.05})   # top3 = 0.25
    current = pd.Series({"A": 0.09, "B": 0.09, "C": 0.08, "D": 0.05})    # -> 0.26
    out = apply_drift_band(target, current, cfg, risk=risk)
    assert out.nlargest(3).sum() <= 0.25 + 1e-9


def test_band_top3_repair_iterates_when_a_retention_promotes():
    """Copilot round-1 finding, verified: forcing the current top-3's upward retentions
    back to target can promote ANOTHER in-band upward retention into the new top-3,
    leaving the cap still breached after a single repair pass. D's retained 0.0865 is
    in-band (4.2% < 5%... using drift_band=0.05 would keep it; band 0.10 here) and after
    A/B/C are forced back to target the new top-3 is D+A+B = 0.2531 > 0.25."""
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.30, drift_band=0.10)
    risk = _rc({"A": "T1", "B": "T2", "C": "T3", "D": "T4"})
    target = pd.Series({"A": 0.0833, "B": 0.0833, "C": 0.0833, "D": 0.083})
    current = pd.Series({"A": 0.086, "B": 0.086, "C": 0.086, "D": 0.0865})
    out = apply_drift_band(target, current, cfg, risk=risk)
    assert out.nlargest(3).sum() <= 0.25 + 1e-9
    validate_book(out, cfg, risk=risk)          # must not raise


def test_band_without_risk_is_byte_identical_to_before():
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, drift_band=0.05)
    target = pd.Series({"A": 0.30, "B": 0.20})
    current = pd.Series({"A": 0.31, "B": 0.0})
    out = apply_drift_band(target, current, cfg)
    assert out["A"] == 0.31 and out["B"] == 0.20              # existing semantics


# ---------------------------------------------------------------- resolve_book(risk=)

def _slate_for(cols, weights, ranks, admit_new=True):
    w = pd.Series(0.0, index=cols)
    r = pd.Series(np.nan, index=cols, dtype=float)
    for s, v in weights.items():
        w[s] = v
    for s, v in ranks.items():
        r[s] = v
    return Slate(weights=w, rank=r, admit_new=admit_new)


def test_resolve_book_with_risk_returns_book_and_scalar_result():
    cols = pd.Index(["A", "B", "C"])
    risk = _rc({"A": "T1", "B": "T2", "C": "T3"}, cols=list(cols), cfg=_LOOSE)
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.25, "B": 0.25}, {"A": 1.0, "B": 2.0})
    book, sres = resolve_book(slate, pd.Series(0.0, index=cols), cfg, risk=risk)
    # sigma 20% per name, independent: sigma_p = 0.2*sqrt(2)*0.25 ~ 7.07% < 10% target
    assert sres.applied_k == 1.0
    assert book["A"] == pytest.approx(0.25)


def test_resolve_book_scalar_cuts_the_whole_book():
    cols = pd.Index(["A", "B"])
    risk = _rc({"A": "T1", "B": "T2"}, cols=list(cols), cfg=_LOOSE)   # var 0.04 each
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.5, "B": 0.5}, {"A": 1.0, "B": 2.0})
    book, sres = resolve_book(slate, pd.Series(0.0, index=cols), cfg, risk=risk)
    sigma_p = np.sqrt(0.25 * 0.04 * 2)                           # 14.14%
    assert sres.applied_k == pytest.approx(min(1.0, 0.10 / sigma_p))
    assert book["A"] == pytest.approx(0.5 * sres.applied_k)


def test_resolve_book_k_move_below_band_still_executes():
    """The suppression regression (risk spec §6): a sub-band k move must pass through."""
    cols = pd.Index(["A", "B"])
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=0.0, drift_band=0.05)
    slate = _slate_for(cols, {"A": 0.5, "B": 0.5}, {"A": 1.0, "B": 2.0})
    risk = _rc({"A": "T1", "B": "T2"}, cols=list(cols), k_prev=0.73, cfg=_LOOSE)
    current = pd.Series({"A": 0.5 * 0.73, "B": 0.5 * 0.73})
    book, sres = resolve_book(slate, current, cfg, risk=risk)
    # k_raw ~ 0.707 -> ~3.2% below k_prev: inside the 5% band, must STILL execute
    assert sres.applied_k == pytest.approx(0.10 / np.sqrt(0.25 * 0.04 * 2))
    assert book["A"] == pytest.approx(0.5 * sres.applied_k)


def test_resolve_book_floor_is_structural_not_post_k():
    """Amendment 2026-08 (blueprint §8 'below => skip signal'): the $1000 floor is an
    eligibility rule on STRUCTURAL weights, applied before the scalar. The old post-k
    placement deleted ATR-parity names exactly when k was low (~0.10 of gross in the
    ablation) — a de-risking decision silently changing which names are held."""
    cols = pd.Index(["A", "B"])
    tight = RiskConfig(top3_cap=1.0, sector_cap=1.0, target_vol=0.05)
    risk = _rc({"A": "T1", "B": "T2"}, cols=list(cols), cfg=tight)
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=1000.0)               # floor_w = 0.02
    slate = _slate_for(cols, {"A": 0.5, "B": 0.028}, {"A": 1.0, "B": 2.0})
    book, sres = resolve_book(slate, pd.Series(0.0, index=cols), cfg, risk=risk)
    assert sres.applied_k < 0.6                 # sigma_p ~ 10%, target 5% -> k ~ 0.5
    # structural 0.028 >= 0.02 -> survives; funded weight MAY sit under floor_w by k
    assert book["B"] == pytest.approx(0.028 * sres.applied_k)
    assert book["B"] < 0.02                     # the semantic change, pinned
    assert book["A"] == pytest.approx(0.5 * sres.applied_k)


def test_resolve_book_structural_subfloor_name_is_dropped_before_scalar():
    """A name under the floor structurally is skipped BEFORE the scalar prices the
    book, so sigma_p reflects only what is actually held (modeled vol == delivered
    structure)."""
    cols = pd.Index(["A", "B"])
    tight = RiskConfig(top3_cap=1.0, sector_cap=1.0, target_vol=0.05)
    risk = _rc({"A": "T1", "B": "T2"}, cols=list(cols), cfg=tight)
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=1000.0)               # floor_w = 0.02
    slate = _slate_for(cols, {"A": 0.5, "B": 0.015}, {"A": 1.0, "B": 2.0})
    book, sres = resolve_book(slate, pd.Series(0.0, index=cols), cfg, risk=risk)
    assert book["B"] == 0.0                     # 0.015 < 0.02 structural -> skipped
    # sigma_p priced on {A: 0.5} alone: sqrt(0.5^2 * 0.04) = 0.10 exactly
    assert sres.sigma_p == pytest.approx(0.10)
    assert book["A"] == pytest.approx(0.5 * sres.applied_k)


def test_resolve_book_entry_barred_blocks_new_but_not_held():
    cols = pd.Index(["A", "B"])
    risk = RiskContext(
        sigma=pd.DataFrame(np.eye(2) * 0.0001, index=list(cols), columns=list(cols)),
        corr=pd.DataFrame(np.eye(2), index=list(cols), columns=list(cols)),
        adv_cap_w=pd.Series(1.0, index=cols), entry_barred=frozenset({"A", "B"}),
        sector=pd.Series({"A": "T1", "B": "T2"}),
        assetid=pd.Series({"A": 1.0, "B": 2.0}), k_prev=1.0, config=RiskConfig())
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.60,
                       min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.3, "B": 0.3}, {"A": 1.0, "B": 2.0})
    current = pd.Series({"A": 0.25, "B": 0.0})
    book, _ = resolve_book(slate, current, cfg, risk=risk)
    assert book["A"] > 0                        # held: retainable despite the bar
    assert book["B"] == 0.0                     # new entry: blocked


def test_resolve_book_without_risk_returns_series_unchanged():
    cols = pd.Index(["A", "B"])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=0.40, min_position_dollars=0.0)
    slate = _slate_for(cols, {"A": 0.3, "B": 0.3}, {"A": 1.0, "B": 2.0})
    out = resolve_book(slate, pd.Series(0.0, index=cols), cfg)
    assert isinstance(out, pd.Series)
