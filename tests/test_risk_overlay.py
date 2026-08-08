import numpy as np
import pandas as pd
import pytest

from number7.engine.strategy import Slate
from number7.risk.overlay import (RiskConfig, RiskContext, ScalarResult,
                                  build_risk_context, ratchet)
from number7.strategies.sizing import SizingConfig


def _ctx(k_prev=1.0, target_vol=0.10, n=3, var=0.04, rho=0.0):
    cols = [f"S{i}" for i in range(n)]
    sig = np.full((n, n), rho * var)
    np.fill_diagonal(sig, var)
    return RiskContext(
        sigma=pd.DataFrame(sig, index=cols, columns=cols),
        corr=pd.DataFrame(np.eye(n), index=cols, columns=cols),
        adv_cap_w=pd.Series(1.0, index=cols),
        entry_barred=frozenset(),
        sector=pd.Series("TestSector", index=cols),
        assetid=pd.Series(np.arange(1.0, n + 1.0), index=cols),
        k_prev=k_prev,
        config=RiskConfig(target_vol=target_vol),
    )


def test_ratchet_down_is_immediate_and_full():
    assert ratchet(0.4, 1.0, 0.10) == 0.4


def test_ratchet_up_is_capped_at_up_step():
    assert ratchet(1.0, 0.4, 0.10) == pytest.approx(0.5)


def test_ratchet_stable_at_one():
    assert ratchet(1.0, 1.0, 0.10) == 1.0


def test_scalar_computes_k_from_portfolio_vol():
    ctx = _ctx(target_vol=0.10, var=0.04, rho=0.0)      # sigma 20% per name
    w = pd.Series({"S0": 0.5, "S1": 0.5, "S2": 0.0})
    sigma_p = np.sqrt(0.5**2 * 0.04 + 0.5**2 * 0.04)    # 14.14%
    res = ctx.scalar(w)
    assert isinstance(res, ScalarResult)
    assert res.sigma_p == pytest.approx(sigma_p)
    assert res.k_raw == pytest.approx(min(1.0, 0.10 / sigma_p))
    assert res.applied_k == res.k_raw                    # k_prev=1, down move


def test_scalar_never_levers_up():
    ctx = _ctx(target_vol=0.50)                          # target far above book vol
    res = ctx.scalar(pd.Series({"S0": 0.3, "S1": 0.3, "S2": 0.3}))
    assert res.k_raw == 1.0 and res.applied_k == 1.0


def test_scalar_frozen_on_empty_book():
    ctx = _ctx(k_prev=0.55)
    res = ctx.scalar(pd.Series(0.0, index=["S0", "S1", "S2"]))
    assert res.applied_k == 0.55                         # frozen, not advanced (spec §6)
    assert res.k_raw == 1.0


def test_k_raw_floor_prevents_underflow():
    ctx = _ctx(var=1e6)                                  # absurd vol = data bug regime
    res = ctx.scalar(pd.Series({"S0": 1.0, "S1": 0.0, "S2": 0.0}))
    assert res.k_raw == pytest.approx(0.01)              # floored, not ~0


def test_scalar_raises_on_funded_weight_without_sigma_row():
    ctx = _ctx()
    w = pd.Series({"S0": 0.5, "GHOST": 0.5})
    with pytest.raises(ValueError, match="GHOST"):
        ctx.scalar(w)


def _slate(weights: dict, cols):
    w = pd.Series(0.0, index=cols)
    rank = pd.Series(np.nan, index=cols, dtype=float)
    for i, (s, v) in enumerate(weights.items()):
        w[s], rank[s] = v, float(i + 1)
    return Slate(weights=w, rank=rank, admit_new=True)


def _view(make_panel, n_days=400, cols=("A", "B", "C", "D"), wide_spread=()):
    rng = np.random.default_rng(11)
    idx = pd.date_range("2024-06-03", periods=n_days, freq="B")
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, (n_days, len(cols))), axis=0)),
        index=idx, columns=list(cols))
    high, low = close * 1.001, close * 0.999
    for s in wide_spread:                       # recent sessions: spread blowout
        high.loc[idx[-25]:, s] = close.loc[idx[-25]:, s] * 1.04
    return make_panel(close, high=high, low=low,
                      gics_sector=pd.Series("TestSector", index=list(cols)))


def test_candidate_set_is_admitted_rank_order_union_held(make_panel):
    view = _view(make_panel, wide_spread=("A",))
    cols = view.px_close.columns
    slate = _slate({"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3}, cols)
    current = pd.Series({"D": 0.10}, index=cols).fillna(0.0)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=2)
    ctx = build_risk_context(view, slate, current, cfg, RiskConfig(), k_prev=1.0)
    # A is spread-blocked and NOT held -> excluded; admitted top-2 = B, C; D is held
    assert "A" in ctx.entry_barred
    assert set(ctx.sigma.index) == {"B", "C", "D"}


def test_held_name_is_in_sigma_even_when_spread_blocked(make_panel):
    view = _view(make_panel, wide_spread=("D",))
    cols = view.px_close.columns
    slate = _slate({"A": 0.3, "B": 0.3, "C": 0.3, "D": 0.3}, cols)
    current = pd.Series({"D": 0.10}, index=cols).fillna(0.0)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=2)
    ctx = build_risk_context(view, slate, current, cfg, RiskConfig(), k_prev=1.0)
    assert "D" in ctx.entry_barred and "D" in ctx.sigma.index


def test_regime_off_candidates_are_held_names_only(make_panel):
    view = _view(make_panel)
    cols = view.px_close.columns
    slate = Slate(weights=pd.Series(0.25, index=cols),
                  rank=pd.Series([1.0, 2.0, 3.0, 4.0], index=cols), admit_new=False)
    current = pd.Series({"C": 0.2}, index=cols).fillna(0.0)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=2)
    ctx = build_risk_context(view, slate, current, cfg, RiskConfig(), k_prev=1.0)
    assert set(ctx.sigma.index) == {"C"}


def test_adv_cap_is_a_weight_ceiling_from_dollar_adv(make_panel):
    view = _view(make_panel)
    cols = view.px_close.columns
    slate = _slate({"A": 0.5, "B": 0.5}, cols)
    cfg = SizingConfig(sleeve_equity=50_000.0, max_positions=5)
    ctx = build_risk_context(view, slate, pd.Series(0.0, index=cols), cfg,
                             RiskConfig(), k_prev=1.0)
    adv = (view.raw_close["A"] * view.volume["A"]).tail(20).mean()
    assert ctx.adv_cap_w["A"] == pytest.approx(0.25 * adv / 50_000.0)


def test_sector_nan_maps_to_unknown(make_panel):
    view = _view(make_panel)
    object.__setattr__(view, "gics_sector",
                       pd.Series({"A": "Energy", "B": None, "C": "Energy", "D": None}))
    cols = view.px_close.columns
    slate = _slate({"A": 0.4, "B": 0.4}, cols)
    ctx = build_risk_context(view, slate, pd.Series(0.0, index=cols),
                             SizingConfig(sleeve_equity=50_000.0), RiskConfig(), 1.0)
    assert ctx.sector["B"] == "UNKNOWN"


def test_raises_on_bad_k_prev_and_accepts_empty_slate(make_panel):
    view = _view(make_panel)
    cols = view.px_close.columns
    slate = _slate({"A": 0.4}, cols)
    zero = pd.Series(0.0, index=cols)
    cfg = SizingConfig(sleeve_equity=50_000.0)
    with pytest.raises(ValueError, match="k_prev"):
        build_risk_context(view, slate, zero, cfg, RiskConfig(), k_prev=0.0)
    empty = Slate(weights=zero, rank=pd.Series(np.nan, index=cols, dtype=float),
                  admit_new=True)
    ctx = build_risk_context(view, empty, zero, cfg, RiskConfig(), 1.0)
    assert len(ctx.sigma) == 0                  # empty slate + flat book is legal (cash)
