"""RiskConfig, RiskContext and the vol-target scalar (risk-layer spec §4-§6).

Every number in RiskConfig is a FROZEN constitution constant declared a priori (spec §5):
zero searched dimensions, zero ledger trials. Changing one is a declared amendment with
Viktor's sign-off - never a tuning loop."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from number7.risk.covariance import ewma_covariance
from number7.risk.spread import spread_gate


@dataclass(frozen=True)
class RiskConfig:
    target_vol: float = 0.10
    up_step: float = 0.10
    ewma_halflife: int = 63
    ewma_window: int = 252
    min_obs: int = 40
    shrinkage: float = 0.30
    sector_cap: float = 0.25
    top3_cap: float = 0.25
    adv_cap: float = 0.25
    adv_window: int = 20
    spread_est_window: int = 21
    spread_base_window: int = 252
    spread_mult: float = 2.0
    spread_floor: float = 0.0010
    beta_band: tuple[float, float] = (0.3, 0.8)
    beta_breach_n: int = 4
    beta_window: int = 252
    k_raw_floor: float = 0.01
    sigma_p_floor: float = 1e-6


@dataclass(frozen=True)
class ScalarResult:
    applied_k: float
    k_raw: float
    sigma_p: float


def ratchet(k_raw: float, k_prev: float, up_step: float) -> float:
    """Anti-procyclicality (spec §3): down moves immediate and in full; up moves capped
    at up_step per rebalance. Never blocks a downward move - the future brakes spec
    composes by pushing k further down, not by fighting this function."""
    if k_raw <= k_prev:
        return k_raw
    return min(k_raw, k_prev + up_step)


@dataclass(frozen=True)
class RiskContext:
    """Everything resolve_book needs from the panel, precomputed (spec §4.4). Plain
    data only - the resolver never touches the panel."""

    sigma: pd.DataFrame          # annualized Σ over the candidate set (spec §4.3)
    corr: pd.DataFrame           # pre-shrinkage correlation, same index
    adv_cap_w: pd.Series         # per-name weight ceiling from the ADV cap
    entry_barred: frozenset      # spread gate AND min_obs bar - block NEW entry only
    sector: pd.Series            # symbol -> label, NaN already mapped to "UNKNOWN"
    assetid: pd.Series           # tie-break key for the top-3 cap (spec §6)
    k_prev: float
    config: RiskConfig

    def scalar(self, w: pd.Series) -> ScalarResult:
        """k for the structural book `w`. Pure: no panel access, no mutation.
        Raises on a funded weight with no Σ row - that is a candidate-set construction
        bug (spec §4.3), never a silent reindex-and-drop, which would understate risk
        exactly during the liquidity-stress episodes that trip the spread gate."""
        funded = w[w > 0]
        missing = [s for s in funded.index if s not in self.sigma.index]
        if missing:
            raise ValueError(
                f"funded names missing from sigma candidate set: {missing[:3]}")
        if len(funded) == 0:
            return ScalarResult(applied_k=self.k_prev, k_raw=1.0, sigma_p=0.0)
        v = funded.to_numpy(dtype=float)
        sub = self.sigma.loc[funded.index, funded.index].to_numpy(dtype=float)
        sigma_p = float(np.sqrt(max(v @ sub @ v, 0.0)))
        if sigma_p < self.config.sigma_p_floor:
            # cash / near-cash book: FREEZE the ratchet (spec §6) - k_prev crawling to
            # 1.0 during a cash period would grant the full-size re-entry that
            # "slow up" exists to forbid.
            return ScalarResult(applied_k=self.k_prev, k_raw=1.0, sigma_p=sigma_p)
        k_raw = float(np.clip(self.config.target_vol / sigma_p,
                              self.config.k_raw_floor, 1.0))
        return ScalarResult(applied_k=ratchet(k_raw, self.k_prev, self.config.up_step),
                            k_raw=k_raw, sigma_p=sigma_p)


def build_risk_context(view, slate, current: pd.Series, sizing, config: RiskConfig,
                       k_prev: float,
                       spread_blocked: pd.DataFrame | None = None) -> RiskContext:
    """The ONLY function that reads the panel (spec §4.1). `view` is already masked to
    the signal date. Candidate set (spec §4.3): the first max_positions names of the
    ADMITTED rank order - the same admission resolve_book performs, computed here from
    the same inputs so the two cannot disagree - UNION all currently held names.

    `spread_blocked` is an optional spread_gate_frame precomputed over the FULL panel;
    its row at the view's last session is exactly spread_gate on the masked view
    (proven per row by the frame's equivalence test), so callers in a loop can pay the
    rolling-median cost once per run instead of once per rebalance."""
    if not 0.0 < k_prev <= 1.0:
        raise ValueError(f"k_prev={k_prev} outside (0, 1]")
    cols = view.px_close.columns
    current = current.reindex(cols).fillna(0.0)
    held = current > 0

    if spread_blocked is None:
        blocked = spread_gate(view.px_high, view.px_low,
                              est_window=config.spread_est_window,
                              base_window=config.spread_base_window,
                              spread_mult=config.spread_mult,
                              spread_floor=config.spread_floor) \
            .reindex(cols).fillna(False)
    else:
        blocked = spread_blocked.loc[view.view_end].reindex(cols).fillna(False)
    obs = view.tr_close.tail(config.ewma_window).notna().sum()
    thin = (obs < config.min_obs).reindex(cols).fillna(True)
    entry_barred = frozenset(cols[blocked | thin])

    eligible = slate.weights > 0
    if not slate.admit_new:
        eligible &= held
    eligible &= held | ~(blocked | thin)        # bars stop NEW entries only
    ranked = slate.rank.where(eligible).dropna().sort_values(kind="mergesort").index
    top = list(ranked[: sizing.max_positions])
    cands = top + [s for s in cols[held] if s not in top]
    if not cands and bool(eligible.any()):
        raise ValueError("empty candidate set against a non-empty admitted slate")

    rets = np.log(view.tr_close[cands]).diff().tail(config.ewma_window)
    cov = ewma_covariance(rets, halflife=config.ewma_halflife, min_obs=config.min_obs,
                          shrinkage=config.shrinkage)
    if cov.sigma.isna().any().any():
        raise ValueError("sigma contains NaN after fallbacks - unusable inputs")

    adv = (view.raw_close[cols] * view.volume[cols]).tail(config.adv_window).mean()
    # float64 is load-bearing: snapshot parquet stores float32, and a float32
    # adv_cap_w promotes min(position_cap, adv_cap_w) to float32, whose 0.1 is
    # 0.10000000149 — above validate_book's position_cap + 1e-9 tolerance.
    adv_cap_w = (config.adv_cap * adv / sizing.sleeve_equity).astype(np.float64) \
        .fillna(0.0)

    return RiskContext(sigma=cov.sigma, corr=cov.corr, adv_cap_w=adv_cap_w,
                       entry_barred=entry_barred,
                       sector=view.gics_sector.reindex(cols).fillna("UNKNOWN"),
                       assetid=view.assetid.reindex(cols),
                       k_prev=k_prev, config=config)


def risk_diagnostics(ctx: RiskContext, view, book: pd.Series,
                     scalar_result: ScalarResult, *, spy: str = "SPY") -> dict:
    """Monitor-only quantities, computed on the RESOLVED book (spec §4.4). NEVER a
    sizing input: beta has no safe automatic action in a long-only book, and avg_corr
    belongs to the future correlation-breakdown brake. The beta-band breach streak
    ("beta_breach_n consecutive out-of-band rebalances") is derived from the recorded
    per-rebalance series by the caller - it is NOT durable state here (spec §4.5)."""
    funded = book[book > 0]
    cfg = ctx.config
    rets = np.log(view.tr_close).diff()
    beta = float("nan")
    if spy in rets.columns and len(funded):
        r_spy = rets[spy].tail(cfg.beta_window)
        r_book = (rets[funded.index].tail(cfg.beta_window) * funded).sum(axis=1)
        var = float(r_spy.var(ddof=0))
        if np.isfinite(var) and var > 0:
            beta = float(r_book.cov(r_spy, ddof=0) / var)
    avg_corr = float("nan")
    both = [s for s in funded.index if s in ctx.corr.index]
    if len(both) >= 2:
        sub = ctx.corr.loc[both, both].to_numpy()
        avg_corr = float(sub[np.triu_indices(len(both), 1)].mean())
    sector_sums = book.groupby(ctx.sector.reindex(book.index)).sum()
    return {
        "applied_k": scalar_result.applied_k, "k_raw": scalar_result.k_raw,
        "sigma_p": scalar_result.sigma_p, "beta": beta, "avg_corr": avg_corr,
        "sector_bound": list(sector_sums[sector_sums >= cfg.sector_cap - 1e-9].index),
        "top3_bound": bool(float(book.nlargest(3).sum()) >= cfg.top3_cap - 1e-9),
        # funded names only: a zero-weight name with adv_cap_w == 0 (no ADV data at
        # the date - delisted or not yet listed) satisfies 0 >= 0 - 1e-9 and would
        # flag every rebalance as adv-bound
        "adv_bound": list(funded.index[funded >= ctx.adv_cap_w
                                       .reindex(funded.index).fillna(np.inf) - 1e-9]),
    }
