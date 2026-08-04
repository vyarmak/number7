from __future__ import annotations

import pandas as pd

from number7.engine.strategy import PanelView, StrategyManifest


class EqualWeightIndex:
    """Gate-6 benchmark (blueprint §6): equal-weight every current index member,
    same schedule, same cost model — defined in code so the gate is computable."""

    def __init__(self, exclude: tuple[str, ...] = ("SPY",)) -> None:
        self.manifest = StrategyManifest(name="ew_index", family="benchmark",
                                         origin="human", params={"exclude": list(exclude)})
        self._exclude = set(exclude)

    def target_weights(self, view: PanelView) -> pd.Series:
        members = view.in_index.iloc[-1]
        picks = [s for s in members.index[members] if s not in self._exclude]
        w = pd.Series(0.0, index=view.px_close.columns)
        if picks:
            w[picks] = 1.0 / len(picks)
        return w


def gate6(candidate_summary: dict, benchmark_summary: dict) -> dict:
    """Coqueret & Guida sniff test: TC-adjusted Sharpe > 2x the EW benchmark => suspect a bug."""
    bs = benchmark_summary.get("sharpe", 0.0)
    ratio = candidate_summary["sharpe"] / bs if bs > 0 else float("inf")
    return {"sharpe_ratio_vs_bench": ratio,
            "suspicious": ratio > 2.0,
            "excess_cagr": candidate_summary["cagr"] - benchmark_summary["cagr"]}
