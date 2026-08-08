import numpy as np
import pandas as pd
import pytest

from number7.risk.overlay import RiskConfig, RiskContext, ScalarResult, ratchet


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
