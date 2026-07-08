from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import PanelView, Strategy


class WFProtocol(BaseModel):
    """Frozen per-family walk-forward protocol (blueprint §6 Gate 3): fixed BEFORE
    testing so the gate cannot be tuned.

    Window semantics: train/test spans define EVALUATION periods. The strategy's
    information set is always the full history up to each signal date — deliberately
    NOT truncated to the window, because (a) lookback signals need burn-in bars from
    before the window, and (b) the live system likewise sees all history. `train_years`
    bounds where IS performance is measured, not what the strategy may read. When a
    family declares fittable parameters, per-window refits must restrict FITTING data
    to the train span at the fitting layer — evaluation slicing stays as-is."""

    model_config = {"frozen": True}
    train_years: int = Field(default=5, gt=0)
    test_months: int = Field(default=12, gt=0)
    step_months: int = Field(default=12, gt=0)     # gt=0 also prevents an infinite loop
    min_windows: int = Field(default=10, gt=0)
    wfe_floor: float = 0.5


@dataclass
class WFReport:
    windows: list[dict] = field(default_factory=list)
    wfe: float = 0.0
    stitched_oos_equity: pd.Series | None = None

    def passes(self, protocol: WFProtocol) -> bool:
        return (len(self.windows) >= protocol.min_windows
                and self.wfe >= protocol.wfe_floor
                and self.stitched_oos_equity is not None
                and float(self.stitched_oos_equity.iloc[-1])
                > float(self.stitched_oos_equity.iloc[0]))


def _annual_log_profit(equity: pd.Series) -> float:
    lp = float(np.log(equity.iloc[-1] / equity.iloc[0]))
    years = max((len(equity) - 1) / 252.0, 1e-9)   # N observations span N-1 return intervals
    return lp / years


def walk_forward(strategy_factory: Callable[[], Strategy], panel: PanelView,
                 protocol: WFProtocol, cost_model: CostModel) -> WFReport:
    """WFE = annualized OOS net log-profit / annualized IS net log-profit
    (Tomasini/Pardo, KB-07 §3), averaged across rolling windows."""
    if protocol.step_months < protocol.test_months:
        raise ValueError("step_months < test_months would overlap OOS windows and "
                         "double-count periods in the stitched equity curve")
    sessions = panel.close.index
    rb_global = weekly_rebalances(sessions)   # ONE schedule, sliced per window — a window
    report = WFReport()                       # starting mid-week must not shift the anchor
    oos_pieces: list[pd.Series] = []
    start = sessions[0]
    while True:
        ahead = sessions[sessions >= start]                   # anchor start to a real session
        if len(ahead) == 0:
            break
        start = ahead[0]
        train_end_raw = start + pd.DateOffset(years=protocol.train_years)
        test_end_raw = train_end_raw + pd.DateOffset(months=protocol.test_months)
        if test_end_raw > sessions[-1]:
            break
        train_end = sessions[sessions <= train_end_raw][-1]   # floored to real sessions,
        test_end = sessions[sessions <= test_end_raw][-1]     # used consistently below
        if test_end <= train_end:                             # degenerate window: no OOS sessions
            start = start + pd.DateOffset(months=protocol.step_months)
            continue
        is_view = panel.masked_to(train_end)
        is_sessions = is_view.close.index[is_view.close.index >= start]
        is_rb = rb_global[(rb_global >= start) & (rb_global <= train_end)]
        is_res = run_backtest(strategy_factory(), is_view, is_rb, cost_model)
        oos_view = panel.masked_to(test_end)
        oos_sessions = oos_view.close.index[oos_view.close.index > train_end]
        oos_rb = rb_global[(rb_global > train_end) & (rb_global <= test_end)]
        oos_res = run_backtest(strategy_factory(), oos_view, oos_rb, cost_model)
        oos_eq = oos_res.equity.loc[oos_sessions]
        if len(is_sessions) < 2 or len(oos_eq) < 2:           # too short to annualize
            start = start + pd.DateOffset(months=protocol.step_months)
            continue
        report.windows.append({
            "train": (str(start.date()), str(train_end.date())),
            "test": (str(oos_eq.index[0].date()), str(test_end.date())),   # actual OOS span
            "is_annual_profit": _annual_log_profit(is_res.equity.loc[is_sessions]),
            "oos_annual_profit": _annual_log_profit(oos_eq),
        })
        oos_pieces.append(np.log(oos_eq / oos_eq.iloc[0]))
        start = start + pd.DateOffset(months=protocol.step_months)

    if report.windows:
        is_avg = float(np.mean([w["is_annual_profit"] for w in report.windows]))
        oos_avg = float(np.mean([w["oos_annual_profit"] for w in report.windows]))
        report.wfe = oos_avg / is_avg if abs(is_avg) > 1e-12 else 0.0
    if oos_pieces:
        chained, level = [], 0.0
        for piece in oos_pieces:
            chained.append(piece + level)
            level = float(chained[-1].iloc[-1])
        report.stitched_oos_equity = np.exp(pd.concat(chained))
    return report
