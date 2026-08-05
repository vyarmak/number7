import numpy as np
import pandas as pd
import pytest

from number7.engine.strategy import Slate
from number7.strategies.sizing import (SizingConfig, apply_drift_band,
                                       holdings_from_shares, resolve_book, validate_book)

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
