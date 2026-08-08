import numpy as np
import pandas as pd
import pytest

from number7.engine.costs import CostModel
from number7.engine.strategy import Slate, StrategyManifest, full_slate
from number7.strategies.sizing import SizingConfig
from number7.validation.walkforward import WFProtocol, walk_forward


class AlwaysLong:
    manifest = StrategyManifest(name="long", family="test", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.px_close.columns)
        w[view.px_close.columns[0]] = 1.0
        return full_slate(w)


class BuysOnlyEarly:
    """Opens positions only in the first half of the panel; afterwards it emits the same
    weights but refuses to admit new names — the regime-off shape that used to zero out
    every OOS fold."""

    manifest = StrategyManifest(name="early", family="test", origin="human", params={})

    def __init__(self, cutoff: pd.Timestamp) -> None:
        self._cutoff = cutoff

    def target_weights(self, view) -> Slate:
        s = full_slate(pd.Series({c: 1.0 if c == view.px_close.columns[0] else 0.0
                                  for c in view.px_close.columns}))
        return Slate(weights=s.weights, rank=s.rank,
                     admit_new=bool(view.view_end <= self._cutoff))


def _drift_panel(make_panel, years=8, mu=0.0004):
    n = int(252 * years)
    dates = pd.date_range("2016-01-04", periods=n, freq="B")
    close = pd.DataFrame({"A": 100 * np.exp(np.cumsum(np.full(n, mu)))}, index=dates)
    return make_panel(close)


def test_walk_forward_on_steady_drift(make_panel):
    protocol = WFProtocol(train_years=3, test_months=6, step_months=6, min_windows=8)
    report = walk_forward(lambda: AlwaysLong(), _drift_panel(make_panel), protocol,
                          CostModel(min_half_spread_bps=0.0))
    assert len(report.windows) >= 8
    assert report.wfe == pytest.approx(1.0, abs=0.15)      # same drift IS and OOS
    assert report.passes(protocol)


def test_overlapping_windows_rejected(make_panel):
    with pytest.raises(ValueError, match="overlap"):
        walk_forward(lambda: AlwaysLong(), _drift_panel(make_panel, years=6),
                     WFProtocol(train_years=3, test_months=12, step_months=6),
                     CostModel(min_half_spread_bps=0.0))


def test_oos_fold_inherits_the_is_end_state(make_panel):
    panel = _drift_panel(make_panel, years=8)
    cutoff = panel.sessions[len(panel.sessions) // 3]
    protocol = WFProtocol(train_years=3, test_months=6, step_months=6, min_windows=8)
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0)
    report = walk_forward(lambda: BuysOnlyEarly(cutoff), panel, protocol,
                          CostModel(min_half_spread_bps=0.0), sizing=cfg)
    # "late" = OOS opens after the cutoff (regime gate off at the fold boundary) AND the
    # fold's own IS window started before the cutoff, so it had a real chance to open the
    # position. Folds whose entire IS window falls after the cutoff can never open in the
    # first place - carrying forward zero state is correct there, not a carry-over bug.
    late = [w for w in report.windows
           if w["train"][0] <= str(cutoff.date()) < w["test"][0]]
    assert late, "test needs folds that open after the cutoff"
    assert all(abs(w["oos_annual_profit"]) > 1e-6 for w in late)


def test_walkforward_carries_final_k_across_folds(make_panel, monkeypatch):
    from number7.engine.strategy import RandomTopN
    from number7.risk.overlay import RiskConfig
    import number7.validation.walkforward as wf
    calls = []
    real = wf.run_backtest

    def spy(*a, **kw):
        calls.append(dict(kw))
        return real(*a, **kw)

    monkeypatch.setattr(wf, "run_backtest", spy)
    panel = _drift_panel(make_panel, years=4)
    protocol = WFProtocol(train_years=1, test_months=6, step_months=6, min_windows=1)
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=1.0,
                       min_position_dollars=0.0)
    walk_forward(lambda: RandomTopN(n=1, seed=1), panel, protocol,
                 CostModel(min_half_spread_bps=0.0), sizing=cfg,
                 risk_cfg=RiskConfig())
    oos_calls = [kw for kw in calls if "initial_weights" in kw]
    assert oos_calls, "test needs at least one OOS fold"
    assert all("initial_k" in kw and kw["initial_k"] is not None for kw in oos_calls)
    assert all(kw.get("risk_cfg") is not None for kw in calls)
