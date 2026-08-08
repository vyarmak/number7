from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

from number7.engine.strategy import Slate, validate_weights

_TOL = 1e-12


@dataclass(frozen=True)
class SizingConfig:
    """Book-resolution configuration (spec §8.1). `sleeve_equity` is the CURRENT sleeve
    equity supplied per call — a fixed book_equity constant is wrong after P&L and wrong
    once the sleeve holds only part of the total book."""

    sleeve_equity: float
    position_cap: float = 0.10          # §8 max single position
    min_position_dollars: float = 1000.0
    gross_max: float = 1.0              # §8 no leverage
    drift_band: float = 0.05
    max_positions: int = 30
    forced_resize_periods: int = 8      # §8.3: re-size a band-held name after N periods


def validate_book(w: pd.Series, config: SizingConfig, name: str = "book",
                  *, risk=None) -> pd.Series:
    """validate_weights PLUS the two limits it does not check. `validate_weights` alone
    tests finite/>=0/sum<=1, so a name retained at 0.104 against a 0.10 cap passes
    undetected (spec §8.3). With `risk` (a RiskContext), additionally enforces the
    overlay limits: sector cap, top-3 cap, per-name ADV cap (risk spec §6 step 10)."""
    validate_weights(w, name=name)
    over = w[w > config.position_cap + 1e-9]
    if len(over):
        raise ValueError(f"{name} breaches position_cap {config.position_cap}: "
                         f"{[(s, round(float(over[s]), 4)) for s in over.index[:3]]}")
    total = float(w.sum())
    if total > config.gross_max + 1e-9:
        raise ValueError(f"{name} gross {total:.4f} > gross_max {config.gross_max}")
    if risk is not None:
        cap = risk.config.sector_cap
        totals = w.groupby(risk.sector.reindex(w.index)).sum()
        bad = totals[totals > cap + 1e-9]
        if len(bad):
            raise ValueError(f"{name} breaches sector cap {cap}: "
                             f"{dict(bad.round(4))}")
        top3 = float(w.nlargest(3).sum())
        if top3 > risk.config.top3_cap + 1e-9:
            raise ValueError(f"{name} breaches top-3 cap: {top3:.4f}")
        over_adv = w[w > risk.adv_cap_w.reindex(w.index).fillna(np.inf) + 1e-9]
        if len(over_adv):
            raise ValueError(f"{name} breaches adv cap: {list(over_adv.index[:3])}")
    return w


def apply_sector_cap(w: pd.Series, sector: pd.Series, cap: float) -> pd.Series:
    """Risk spec §6 step 4: scale each breaching sector down proportionally. Shortfall
    goes to cash, NEVER redistributed - redistribution would hand weight to lower-ranked
    names the budgeted fill did not choose (a second, hidden fill)."""
    out = w.copy()
    labels = sector.reindex(w.index)
    totals = w.groupby(labels).sum()
    for sec, total in totals.items():
        if total > cap + _TOL:
            members = labels == sec
            out[members] *= cap / total
    return out


def apply_top3_cap(w: pd.Series, cap: float, assetid: pd.Series,
                   max_iter: int) -> pd.Series:
    """Risk spec §6 step 5 with the termination contract: deterministic tie-break by
    (-weight, assetid) under a stable sort; hard iteration cap; final direct check.
    Scaling the 3 largest can promote a 4th name into the top 3, hence the loop."""
    def _top3(v: pd.Series) -> pd.Index:
        order = pd.DataFrame({"w": -v, "aid": assetid.reindex(v.index)}) \
            .sort_values(["w", "aid"], kind="mergesort")
        return order.index[:3]

    out = w.copy()
    for _ in range(max_iter):
        top = _top3(out)
        total = float(out[top].sum())
        if total <= cap + _TOL:
            return out
        out[top] *= cap / total
    if float(out[_top3(out)].sum()) > cap + _TOL:
        raise RuntimeError(f"top-3 cap failed to converge in {max_iter} iterations")
    return out


def apply_drift_band(target: pd.Series, current: pd.Series, config: SizingConfig,
                     stale_periods: pd.Series | None = None, risk=None) -> pd.Series:
    """Relative band on names held and still held: keep `current` when
    |target - current| / target <= drift_band. Entries and exits always execute.

    Post-band re-validation is MANDATORY: the band runs after normalization and can
    re-violate both limits (spec §8.3). A relative band also bites five times harder on a
    10% position than a 2% one, and a name can drift within band indefinitely — hence the
    forced re-size after `forced_resize_periods`.

    Precondition: `target.sum() <= config.gross_max` on entry (always true via
    `resolve_book`) — without it, the gross-breach `while` loop below is not guaranteed
    to terminate with the gross constraint satisfied."""
    current = current.reindex(target.index).fillna(0.0)
    stale = (pd.Series(0, index=target.index) if stale_periods is None
             else stale_periods.reindex(target.index).fillna(0))
    both = (target > 0) & (current > 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        rel = (target - current).abs() / target.where(target > 0)
    keep = both & (rel <= config.drift_band) & (stale < config.forced_resize_periods)
    out = target.where(~keep, current)

    breach = keep & (out > config.position_cap + 1e-9)      # retention breaches the cap
    out[breach] = target[breach]
    keep = keep & ~breach
    if risk is not None:
        # generalized repair (risk spec §6): retention must not re-breach ANY cap on
        # the structural book. Only upward retentions (out > target) can raise a sum,
        # so forcing them back to target restores the cap-satisfying value the caps
        # stage produced. validate_book(risk=...) is the backstop proof.
        over_adv = keep & (out > risk.adv_cap_w.reindex(out.index).fillna(np.inf) + 1e-9)
        out[over_adv] = target[over_adv]
        keep = keep & ~over_adv

        sec = risk.sector.reindex(out.index)
        totals = out.groupby(sec).sum()
        for s in totals[totals > risk.config.sector_cap + 1e-9].index:
            fix = keep & (sec == s) & (out > target)
            out[fix] = target[fix]
            keep = keep & ~fix

        order = pd.DataFrame({"w": -out, "aid": risk.assetid.reindex(out.index)}) \
            .sort_values(["w", "aid"], kind="mergesort")
        top = order.index[:3]
        if float(out[top].sum()) > risk.config.top3_cap + 1e-9:
            fix = keep & out.index.isin(top) & (out > target)
            out[fix] = target[fix]
            keep = keep & ~fix
    while float(out.sum()) > config.gross_max + 1e-9 and bool(keep.any()):
        worst = (out - target).where(keep).idxmax()          # largest upward retention
        out[worst], keep[worst] = target[worst], False
    return out


def resolve_book(slate: Slate, current: pd.Series, config: SizingConfig,
                 stale_periods: pd.Series | None = None, *, risk=None):
    """risk=None (spec §8.2, UNCHANGED): admission -> budgeted top-down fill -> cap ->
    gross normalization -> floor -> drift band -> re-validate; returns the book Series.

    With a RiskContext (risk spec §6, order normative): admission+entry bars -> fill ->
    min(position, ADV) cap -> sector cap -> top-3 cap -> gross -> STRUCTURAL drift band
    -> vol scalar -> floor -> re-validate; returns (book, ScalarResult).

    Called identically by run_backtest and compute_live_targets. `current` is always
    state_at_signal (T-1), never state_at_fill: live trading cannot know T's closing
    weights when the MOC order is submitted that morning (spec §5.3)."""
    idx = slate.weights.index
    current = current.reindex(idx).fillna(0.0)

    # 1. admission — regime-off funds retained names, it does not freeze the book.
    #    Entry bars (spread gate, min_obs) block NEW entries only (risk spec §6).
    eligible = slate.weights > 0
    if not slate.admit_new:
        eligible &= current > 0
    if risk is not None:
        barred = idx.isin(risk.entry_barred)
        eligible &= (current > 0) | ~barred

    # 2. budgeted top-down fill; the marginal name is SKIPPED, not partially filled,
    #    and the walk terminates there so rank priority is never inverted. The budget
    #    here is full sleeve equity (1.0) -- "equity is exhausted", not gross_max, which
    #    is a distinct later step (4); using gross_max here would let a tight gross_max
    #    starve the fill before normalization ever runs.
    ranked = slate.rank.where(eligible).dropna().sort_values(kind="mergesort").index
    target = pd.Series(0.0, index=idx)
    used, n = 0.0, 0
    for sym in ranked:
        if n >= config.max_positions:
            break
        w = float(slate.weights[sym])
        if used + w > 1.0 + _TOL:
            break
        target[sym], used, n = w, used + w, n + 1

    # 3. position cap (per-name min with the ADV cap when the overlay is on)
    cap = config.position_cap
    if risk is not None:
        cap = np.minimum(cap, risk.adv_cap_w.reindex(idx).fillna(0.0))
    target = target.clip(upper=cap)

    # 4-5. sector and top-3 caps (risk spec §6 steps 4-5)
    if risk is not None:
        target = apply_sector_cap(target, risk.sector, risk.config.sector_cap)
        target = apply_top3_cap(target, risk.config.top3_cap, risk.assetid,
                                max_iter=config.max_positions)

    # 6. gross normalization (scale-DOWN only: the risk pipeline's scaling invariant
    #    depends on no stage between the caps and the scalar ever scaling UP)
    gross = float(target.sum())
    if gross > config.gross_max:
        target *= config.gross_max / gross

    if risk is None:
        # 5. floor, AFTER all scalars — normalization can push a surviving $1,050
        #    position below $1,000. Dropping only lowers the sum, so one pass IS the
        #    fixed point; the shortfall stays in cash.
        floor_w = config.min_position_dollars / config.sleeve_equity
        target[target < floor_w] = 0.0

        # 6. drift band, then re-validate
        return validate_book(apply_drift_band(target, current, config, stale_periods),
                             config, name="resolved_book")

    # 7. STRUCTURAL drift band: compare against holdings descaled by the k that
    #    produced them (risk spec §6 "Why the band moved before the scalar") — band
    #    decisions become k-independent, so every k move executes in full.
    structural_current = current / risk.k_prev
    banded = apply_drift_band(target, structural_current, config, stale_periods,
                              risk=risk)

    # 8. vol scalar on the structural post-cap book
    res = risk.scalar(banded)
    scaled = banded * res.applied_k

    # 9. floor AFTER all scalars (k can push a surviving position under $1k; dropping
    #    only lowers the sum, one pass remains the fixed point)
    floor_w = config.min_position_dollars / config.sleeve_equity
    scaled[scaled < floor_w] = 0.0

    # 10. re-validate with the risk limits
    return (validate_book(scaled, config, name="resolved_book", risk=risk), res)


def holdings_from_shares(shares: Mapping[str, float], raw_close: pd.Series,
                         sleeve_equity: float) -> pd.Series:
    """Live-path `current` (spec §8.4): broker SHARE COUNTS x the snapshot's T-1 official
    close / sleeve equity — never broker market value. The backtest marks holdings at
    T-1's close while the live path runs on the morning of T; broker market value would
    mark after the open, so golden replay would pass on a fixture while the live path
    silently diverged intraday.

    Callers must NOT invoke this with a partial or stale broker snapshot: stale broker
    truth degrades to hold-state / no trades, because a misread `current_i > 0` mask
    converts a designed hold-through-drawdown into an accidental full exit."""
    held = pd.Series(shares, dtype=float).reindex(raw_close.index).fillna(0.0)
    return (held * raw_close / sleeve_equity).fillna(0.0)
