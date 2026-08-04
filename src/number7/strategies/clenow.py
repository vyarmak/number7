from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from number7.engine.strategy import PanelView, Slate, StrategyManifest

ANN_FACTOR = 250            # PINNED (spec OQ-2). NOT a parameter: the exponential is applied
# before the R^2 multiply, so varying it REORDERS names. Excluded from the searched space.
ATR_BURN_IN_MULT = 5        # PINNED burn-in: ATR is recursed over atr_window * 5 true ranges
# after the seed, so the value is not seed-dominated and the known-answer test has a
# unique answer (spec §6.5).


def slope_r2(log_px: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS of each column of `log_px` on the ORDINAL session index 0..n-1 (spec §6.1).
    Ordinal rather than calendar spacing is intentional and matches the published method —
    do not "fix" it.

    R^2 here is a SMOOTHNESS HEURISTIC, not a significance measure: regressing a near-random
    walk on time is textbook spurious regression and a driftless walk has substantial
    expected R^2 over 90 sessions. That is intentional in the published system. Nobody
    should later upgrade it to a t-statistic or p-value gate."""
    n = log_px.shape[0]
    xc = np.arange(n, dtype=float)
    xc -= xc.mean()
    sxx = float((xc ** 2).sum())
    yc = log_px - log_px.mean(axis=0)
    slope = (xc[:, None] * yc).sum(axis=0) / sxx
    ss_tot = (yc ** 2).sum(axis=0)
    # A genuinely constant column accumulates float64 rounding noise in ss_tot rather than
    # an exact zero (mean-then-subtract does not cancel perfectly), so compare against a
    # tolerance scaled to the data's magnitude instead of a bare "> 0".
    tol = np.finfo(float).eps * n * np.maximum((log_px ** 2).mean(axis=0), 1.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        r2 = np.where(ss_tot > tol, 1.0 - (ss_tot - slope ** 2 * sxx) / ss_tot, np.nan)
    return slope, r2          # constant log-price -> ss_tot ~ 0 -> R^2 NaN -> ineligible


def wilder_atr(high: pd.DataFrame, low: pd.DataFrame, close: pd.DataFrame,
               window: int) -> pd.Series:
    """Latest ATR per column with Wilder smoothing, PINNED (spec §6.5):
    seed ATR_n = mean(TR_1..TR_n), then ATR_t = ((n-1) * ATR_{t-1} + TR_t) / n.
    Simple-mean smoothing is a robustness DIAGNOSTIC, not a parameter — Wilder's
    alpha = 1/n implies an effective span near 2n, a materially different system.

    All three inputs must share one basis; mixing an adjusted close with raw high/low
    manufactures true ranges around every corporate action."""
    prev = close.shift(1)
    tr = np.maximum(high - low, np.maximum((high - prev).abs(), (low - prev).abs()))
    tr = tr.iloc[1:].tail(window * ATR_BURN_IN_MULT)      # first bar has no prev close
    if len(tr) < window:
        return pd.Series(np.nan, index=close.columns)
    base = tr.iloc[window - 1:].copy()
    base.iloc[0] = tr.iloc[:window].mean()                # pinned seed
    return base.ewm(alpha=1.0 / window, adjust=False).mean().iloc[-1]


@dataclass(frozen=True)
class ClenowParams:
    lookback: int = 90
    atr_window: int = 20
    ma_filter: int = 100
    regime_ma: int = 200
    gap_threshold: float = 0.15          # OVERNIGHT gap definition (spec §6.2)
    risk_factor: float = 0.001           # 10bp of equity per position PER UNIT OF ATR
    hold_top_pct: float = 0.20
    regime_symbol: str = "SPY"
    # Diagnostic switches (spec §11.2 ablations). NOT searched parameters.
    use_r2: bool = True
    use_regime: bool = True
    use_gap_filter: bool = True
    equal_weight: bool = False
    equal_weight_size: float = 0.04


class ClenowMomentum:
    """Clenow equity momentum (KB-02, KB-08, KB-11 §9a), STATELESS: a pure function of the
    panel. Admission, budgeting, caps, floor and the drift band live in sizing.resolve_book,
    which is what keeps truncate-and-compare a total causality proof (spec §5.2).

    `shuffle_seed` turns the strategy into the MATCHED monkey null (spec §10.2): the score
    vector is permuted among scoreable constituents, so ranking information is destroyed
    while eligibility filters, the regime gate, ATR sizing and resolution stay identical.
    The RNG is seeded on (seed, date) so the null is a pure function of the date — not the
    call-count-dependent construction in RandomTopN (spec §15)."""

    def __init__(self, params: ClenowParams, shuffle_seed: int | None = None) -> None:
        self.p = params
        self.shuffle_seed = shuffle_seed
        name = "clenow" if shuffle_seed is None else f"clenow_shuffled_{shuffle_seed}"
        self.manifest = StrategyManifest(
            name=name, family="null" if shuffle_seed is not None else "clenow_momentum",
            origin="human", params={**asdict(params), "ann_factor": ANN_FACTOR,
                                    "atr_burn_in_mult": ATR_BURN_IN_MULT},
            reentry_blackout_days=0)   # recorded decision, Clenow-faithful (spec §6.6)

    @property
    def _need(self) -> int:
        return max(self.p.lookback, self.p.ma_filter,
                   self.p.atr_window * ATR_BURN_IN_MULT + 1)

    def target_weights(self, view: PanelView) -> Slate:
        p, cols = self.p, view.px_close.columns
        weights = pd.Series(0.0, index=cols)
        rank_out = pd.Series(np.nan, index=cols, dtype=float)

        members = view.in_index.iloc[-1]
        names = list(members.index[members])          # constituents only: the regime
        if not names:                                 # instrument and every other extra
            return Slate(weights, rank_out, self._admit(view))   # are excluded (§6.2)
        px = view.px_close[names]
        if len(px) < self._need:
            return Slate(weights, rank_out, self._admit(view))

        # --- preconditions (§6.3): no silent NaN path into ranking. Each series must be
        # NaN-free over the window it is actually consumed in, not just close: a gap in
        # high/low or open silently COMPRESSES the ATR/gap window instead of disqualifying
        # (e.g. ewm quietly skipping the missing bar) -- exactly what §6.3 forbids. ---
        tail = px.tail(self._need)
        valid = tail.notna().all() & (tail > 0).all()
        m = p.atr_window * ATR_BURN_IN_MULT + 1
        valid &= view.px_high[names].tail(m).notna().all()
        valid &= view.px_low[names].tail(m).notna().all()
        if p.use_gap_filter:
            valid &= view.px_open[names].tail(p.lookback).notna().all()

        # --- score over the whole constituent set, THEN qualifiers (§6.2) ---
        # log of an ineligible non-positive close is NaN by construction (masked by
        # `valid` below); suppress the resulting benign RuntimeWarning.
        with np.errstate(invalid="ignore"):
            lb = np.log(px.tail(p.lookback).to_numpy(dtype=float))
        slope, r2 = slope_r2(lb)
        ann = np.expm1(slope * ANN_FACTOR)
        raw = ann * r2 if p.use_r2 else ann
        score = pd.Series(raw, index=names).where(valid)
        if self.shuffle_seed is not None:
            rng = np.random.default_rng([self.shuffle_seed, view.view_end.toordinal()])
            scored = score.dropna().index
            score.loc[scored] = rng.permutation(score.loc[scored].to_numpy())

        aid = view.assetid.reindex(names).astype(float).fillna(np.inf)
        order = pd.DataFrame({"score": score, "aid": aid}).sort_values(
            ["score", "aid"], ascending=[False, True], kind="mergesort", na_position="last")
        rank = pd.Series(np.arange(1.0, len(order) + 1.0), index=order.index)
        rank[score.isna()] = np.nan          # unscoreable names are unrankable, not rank 1
        rank_out[names] = rank.reindex(names)

        # --- qualifiers, applied AFTER ranking: a name that fails a filter does not
        # promote the names below it (§6.2) ---
        cutoff = math.floor(p.hold_top_pct * len(names))
        q = valid & rank.reindex(names).le(cutoff)
        q &= px.iloc[-1] > px.tail(p.ma_filter).mean()
        if p.use_gap_filter:
            gap = (view.px_open[names] / px.shift(1) - 1.0).abs().tail(p.lookback)
            q &= ~(gap > p.gap_threshold).any()

        atr = wilder_atr(view.px_high[names].tail(m), view.px_low[names].tail(m),
                         px.tail(m), p.atr_window)
        q &= atr.gt(0.0).fillna(False)                # zero/NaN ATR -> never an infinite

        elig = list(q.fillna(False).index[q.fillna(False)])   # position
        if elig:
            if p.equal_weight:
                weights[elig] = p.equal_weight_size
            else:
                # ABSOLUTE, not proportional (§6.5). risk_factor is 10bp of equity per
                # position PER UNIT OF ATR; the resulting weight depends on close/ATR,
                # which varies enormously across names. Normalizing here would cancel
                # risk_factor and destroy the emergent position count.
                weights[elig] = (p.risk_factor * px.iloc[-1][elig] / atr[elig]).astype(float)
        return Slate(weights=weights, rank=rank_out, admit_new=self._admit(view))

    def _admit(self, view: PanelView) -> bool:
        """Regime gate (§6.4). Semantics are precisely allow_open_new_symbols = False —
        NOT "no buy orders" and NOT "the book never grows": retained names are still
        re-sized by current ATR parity, which can increase share counts in a downtrend.

        Warm-up is an EXPLICIT branch, not a NaN side effect: `NaN > x` is False, which
        would fall into regime-off by accident rather than by design. No hysteresis — the
        gate is entry-only, which bounds whipsaw cost."""
        p = self.p
        if not p.use_regime:
            return True
        if p.regime_symbol not in view.px_close.columns:
            return False                       # fail-safe: no regime series, no new names
        tail = view.px_close[p.regime_symbol].tail(p.regime_ma)
        if len(tail) < p.regime_ma or not bool(tail.notna().all()):
            return False                       # warm-up
        return bool(tail.iloc[-1] > tail.mean())
