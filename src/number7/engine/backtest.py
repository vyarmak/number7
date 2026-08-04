from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
import pandas as pd

from number7.engine.costs import CostModel
from number7.engine.schedule import signal_date
from number7.engine.strategy import PanelView, Slate, Strategy, mask_unquoted, validate_weights
from number7.strategies.sizing import SizingConfig, resolve_book


@dataclass
class BacktestResult:
    equity: pd.Series
    weights: pd.DataFrame                 # resolved book decided at each rebalance
    turnover: pd.Series
    costs: pd.Series
    rebalance_dates: pd.DatetimeIndex
    state_at_signal: pd.DataFrame         # holdings as of T-1 close (what the resolver saw)
    stale_periods: pd.DataFrame           # consecutive band-held periods, as of T-1
    equity_at_signal: pd.Series           # sleeve equity as of T-1 close
    delisting_exits: pd.Series            # held names with no quote at the signal date
    final_weights: pd.Series              # post-loop book, for walk-forward fold carry-over
    final_stale: pd.Series
    slates: dict[pd.Timestamp, Slate] | None = None


def _one_way(cost_model: CostModel, panel: PanelView, asof: pd.Timestamp,
             sym: str, dw: float, equity: float) -> float:
    """Cost inputs (sigma, ADV) use data through `asof` = the SIGNAL date, not the
    execution session — the live path submits before t's close exists (§4.1 contract).
    Sigma is measured on the capital-adjusted basis (dividend drift is not volatility);
    ADV is a traded-notional quantity, so it uses raw price x raw volume."""
    sigma = float(np.log(panel.px_close[sym]).diff().loc[:asof].tail(63).std() or 0.0)
    if not np.isfinite(sigma):
        sigma = 0.0
    adv = float((panel.raw_close[sym] * panel.volume[sym]).loc[:asof].tail(20).mean())
    q_over_adv = 0.0 if not np.isfinite(adv) or adv <= 0 else abs(dw) * equity / adv
    return cost_model.one_way_cost(spread_est=0.0, q_over_adv=q_over_adv, sigma=sigma)


def run_backtest(strategy: Strategy, panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                 cost_model: CostModel, *, sizing: SizingConfig | None = None,
                 initial: float = 1.0, cash_annual_rate: float = 0.0,
                 start: pd.Timestamp | None = None,
                 initial_weights: pd.Series | None = None,
                 initial_stale: pd.Series | None = None,
                 record_slates: bool = False) -> BacktestResult:
    """Causal weekly-cadence engine (blueprint §4.1). `sizing=None` is passthrough: the
    slate's weights are the book, which is what benchmarks and null fixtures want. With a
    SizingConfig, the same resolve_book the live path calls decides the book.

    `start` limits the SIMULATED sessions without truncating the information set — signals
    still read the full history behind them. Walk-forward uses it with `initial_weights` so
    an OOS fold inherits the IS end-state instead of opening flat.

    KNOWN OPTIMISTIC ASSUMPTION (spec §9): the loop sets w = target after observing T's
    return, assuming exact closing-weight attainment from a morning-submitted MOC order.
    Not a signal leak; the paper phase will measure it."""
    sessions = panel.sessions
    cols = panel.tr_close.columns
    rets = panel.tr_close.pct_change().fillna(0.0)
    cash_daily = (1.0 + cash_annual_rate) ** (1.0 / 252.0) - 1.0
    loop = sessions if start is None else sessions[sessions >= start]

    equity = pd.Series(np.nan, index=sessions, dtype=float)
    decided: dict[pd.Timestamp, pd.Series] = {}
    signal_state: dict[pd.Timestamp, pd.Series] = {}
    signal_stale: dict[pd.Timestamp, pd.Series] = {}
    signal_equity: dict[pd.Timestamp, float] = {}
    delisted: dict[pd.Timestamp, int] = {}
    turnover: dict[pd.Timestamp, float] = {}
    costs: dict[pd.Timestamp, float] = {}
    slates: dict[pd.Timestamp, Slate] = {}

    w = (pd.Series(0.0, index=cols) if initial_weights is None
         else initial_weights.reindex(cols).fillna(0.0))
    stale = (pd.Series(0, index=cols, dtype=int) if initial_stale is None
             else initial_stale.reindex(cols).fillna(0).astype(int))
    eq = initial
    rb = set(rebalance_dates)

    for t in loop:
        state_at_signal, eq_at_signal = w.copy(), eq   # T-1 close: captured BEFORE the
        cash = 1.0 - float(w.sum())                    # earn/drift lines (spec §5.3)
        eq *= float(1.0 + (w * rets.loc[t]).sum() + cash * cash_daily)
        if float(w.sum()) > 0:
            grown = w * (1.0 + rets.loc[t])
            port = float(grown.sum() + cash * (1.0 + cash_daily))
            w = grown / port
        if t in rb and t != sessions[0]:      # first session has no signal date - skip
            sig = signal_date(sessions, t)
            view = panel.masked_to(sig)
            slate = strategy.target_weights(view)
            if record_slates:
                slates[t] = slate
            tradeable = mask_unquoted(slate, panel, sig, cols)
            if sizing is None:
                target = validate_weights(tradeable.weights, name=strategy.manifest.name)
            else:
                cfg = replace(sizing, sleeve_equity=eq_at_signal)
                target = resolve_book(tradeable, state_at_signal, cfg,
                                      stale).reindex(cols).fillna(0.0)
            # Orders are sized from T-1 information — that is exactly what the live path
            # submits, so a drift-band retention costs nothing and moves nothing.
            dw = (target - state_at_signal).abs()
            c = float(sum(_one_way(cost_model, panel, sig, s, float(dw[s]), eq) * float(dw[s])
                          for s in dw.index[dw > 0]))
            if c >= 1.0:      # costs consuming the whole book = broken cost model/sizing
                raise RuntimeError(f"rebalance cost fraction {c:.3f} >= 1.0 at {t.date()} - "
                                   "cost model or position sizing is misconfigured")
            eq *= 1.0 - c
            traded = dw > 1e-12
            stale = pd.Series(np.where(traded | (target <= 0), 0, stale + 1),
                              index=cols, dtype=int)
            signal_state[t], signal_stale[t] = state_at_signal, stale.copy()
            signal_equity[t] = eq_at_signal
            delisted[t] = int(((state_at_signal > 0)
                               & panel.tr_close.loc[sig].isna()).sum())
            turnover[t], costs[t], decided[t] = float(dw.sum()), c, target
            w = target.copy()
        equity.loc[t] = eq

    return BacktestResult(
        equity=equity,
        weights=pd.DataFrame(decided).T if decided else pd.DataFrame(columns=cols),
        turnover=pd.Series(turnover, dtype=float),
        costs=pd.Series(costs, dtype=float),
        rebalance_dates=pd.DatetimeIndex(sorted(decided)),   # executed only (skips excluded)
        state_at_signal=pd.DataFrame(signal_state).T if signal_state
        else pd.DataFrame(columns=cols),
        stale_periods=pd.DataFrame(signal_stale).T if signal_stale
        else pd.DataFrame(columns=cols),
        equity_at_signal=pd.Series(signal_equity, dtype=float),
        delisting_exits=pd.Series(delisted, dtype=float),
        final_weights=w,
        final_stale=stale,
        slates=slates if record_slates else None,
    )


def summary(result: BacktestResult) -> dict:
    eq = result.equity.dropna()
    r = np.log(eq).diff().dropna()
    years = max(len(r) / 252.0, 1e-9)
    ann = float(r.mean() * 252)
    vol = float(r.std(ddof=0) * np.sqrt(252))
    downside_arr = r[r < 0]
    downside = float(downside_arr.std(ddof=0) * np.sqrt(252)) if len(downside_arr) else np.nan
    dd = float((eq / eq.cummax() - 1.0).min())
    gains, losses = float(r[r > 0].sum()), float(-r[r < 0].sum())
    return {
        "cagr": float(eq.iloc[-1] ** (1 / years) - 1),
        "sharpe": ann / vol if vol > 0 else 0.0,
        "sortino": ann / downside if downside and downside > 0 else 0.0,
        "max_dd": dd,
        "profit_factor": gains / losses if losses > 0 else np.inf,
        "hit_rate": float((r > 0).mean()) if len(r) else 0.0,
        "n_rebalances": int(len(result.rebalance_dates)),
        "avg_turnover": float(result.turnover.mean()) if len(result.turnover) else 0.0,
    }
