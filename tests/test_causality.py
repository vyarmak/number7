import numpy as np
import pandas as pd

from number7.engine.costs import CostModel
from number7.engine.live import build_panel
from number7.engine.strategy import (
    LookaheadTrap,
    PanelView,
    RandomTopN,
    Slate,
    StrategyManifest,
)
from number7.strategies.sizing import SizingConfig
from number7.validation.causality import causality_violations, closed_loop_violations


def _walk_panel(make_panel, n=10, n_sym=4, seed=13) -> PanelView:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-06-01", periods=n, freq="B")
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, n_sym)), axis=0)),
                         index=dates, columns=[f"S{i}" for i in range(n_sym)])
    return make_panel(close)


class TrajectoryLeak:
    """Pure at any single point, but its ADMISSION gate reads the last bar of its stored
    panel — so the trajectory diverges even though pointwise weights can match."""

    manifest = StrategyManifest(name="traj_leak", family="trap", origin="human", params={})

    def __init__(self, panel) -> None:
        self._end = panel.px_close.iloc[-1].mean()

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w[view.px_close.columns[0]] = 0.5
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank[view.px_close.columns[0]] = 1.0
        return Slate(weights=w, rank=rank,
                     admit_new=bool(view.px_close.iloc[-1].mean() < self._end))


def test_closed_loop_clean_for_a_causal_strategy(make_panel):
    panel = _walk_panel(make_panel, n=40)
    rb = pd.DatetimeIndex(panel.sessions[5::5])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0)
    assert closed_loop_violations(lambda p: RandomTopN(n=1, seed=5), panel, rb,
                                  CostModel(), sizing=cfg, truncate_last_n=5) == []


def test_closed_loop_catches_a_trajectory_leak(make_panel):
    panel = _walk_panel(make_panel, n=40)
    rb = pd.DatetimeIndex(panel.sessions[5::5])
    cfg = SizingConfig(sleeve_equity=1.0, position_cap=1.0, min_position_dollars=0.0)
    bad = closed_loop_violations(lambda p: TrajectoryLeak(p), panel, rb,
                                 CostModel(), sizing=cfg, truncate_last_n=10)
    assert bad


def test_causal_strategy_is_clean(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.sessions[1], panel.sessions[2]])
    v = causality_violations(lambda p: RandomTopN(n=1, seed=5), panel, rb,
                             truncate_last_n=1)
    assert v == []


def test_lookahead_trap_is_caught(make_panel):
    panel = _walk_panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[3], panel.sessions[5]])
    v = causality_violations(lambda p: LookaheadTrap(n=1, full_close=p.px_close),
                             panel, rb, truncate_last_n=3)
    assert len(v) >= 1


def test_truncate_last_n_validated(make_panel):
    import pytest
    panel = _walk_panel(make_panel)
    rb = pd.DatetimeIndex([panel.sessions[3]])
    with pytest.raises(ValueError, match="truncate_last_n"):
        causality_violations(lambda p: RandomTopN(n=1, seed=5), panel, rb,
                             truncate_last_n=len(panel.sessions))
