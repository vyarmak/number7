from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from number7.engine.costs import CostModel
from number7.engine.schedule import signal_date
from number7.engine.strategy import PanelView, Strategy


@dataclass
class BacktestResult:
    equity: pd.Series
    weights: pd.DataFrame
    turnover: pd.Series
    costs: pd.Series
    rebalance_dates: pd.DatetimeIndex


def _one_way(cost_model: CostModel, panel: PanelView, t: pd.Timestamp,
             sym: str, dw: float, equity: float) -> float:
    sigma = float(np.log(panel.close[sym]).diff().loc[:t].tail(63).std() or 0.0)
    if not np.isfinite(sigma):
        sigma = 0.0
    adv = float((panel.unadjusted_close[sym] * panel.volume[sym]).loc[:t].tail(20).mean())
    q_over_adv = 0.0 if not np.isfinite(adv) or adv <= 0 else abs(dw) * equity / adv
    return cost_model.one_way_cost(spread_est=0.0, q_over_adv=q_over_adv, sigma=sigma)


def run_backtest(strategy: Strategy, panel: PanelView, rebalance_dates: pd.DatetimeIndex,
                 cost_model: CostModel, initial: float = 1.0) -> BacktestResult:
    sessions = panel.close.index
    rets = panel.close.pct_change().fillna(0.0)
    equity = pd.Series(np.nan, index=sessions, dtype=float)
    decided: dict[pd.Timestamp, pd.Series] = {}
    turnover: dict[pd.Timestamp, float] = {}
    costs: dict[pd.Timestamp, float] = {}

    w = pd.Series(0.0, index=panel.close.columns)   # start in cash
    eq = initial
    rb = set(rebalance_dates)

    for t in sessions:
        eq *= float(1.0 + (w * rets.loc[t]).sum())          # earn today with yesterday's book
        if float(w.sum()) > 0:                               # drift weights with returns
            grown = w * (1.0 + rets.loc[t])
            port = float(grown.sum() + (1.0 - w.sum()))      # cash leg grows at 0
            w = grown / port
        if t in rb and t != sessions[0]:      # first session has no signal date - skip
            view = panel.masked_to(signal_date(sessions, t))
            target = strategy.target_weights(view).reindex(w.index).fillna(0.0)
            dw = (target - w).abs()
            c = float(sum(_one_way(cost_model, panel, t, s, float(dw[s]), eq) * float(dw[s])
                          for s in dw.index[dw > 0]))
            eq *= 1.0 - c
            turnover[t], costs[t], decided[t] = float(dw.sum()), c, target
            w = target.copy()
        equity.loc[t] = eq

    return BacktestResult(
        equity=equity,
        weights=pd.DataFrame(decided).T if decided
        else pd.DataFrame(columns=panel.close.columns),
        turnover=pd.Series(turnover, dtype=float),
        costs=pd.Series(costs, dtype=float),
        rebalance_dates=pd.DatetimeIndex(sorted(rb)),
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
