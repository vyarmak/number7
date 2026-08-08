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
    """Pure at any single point (weights and rank never depend on `view`), but its
    ADMISSION gate is decided ONCE, at construction, from the LAST bar of its stored
    panel relative to the FIRST — a leak of how far the data series extends, which a
    causal strategy cannot observe. Because it's fixed for the run rather than
    re-evaluated per view, full and truncated disagree on it from the very FIRST
    rebalance, while S0 is not yet held by either — a real entry-vs-no-entry split, not
    a later disagreement over an already-funded position. That split cascades into every
    later resolved book, signal-time state and the equity trajectory."""

    manifest = StrategyManifest(name="traj_leak", family="trap", origin="human", params={})

    def __init__(self, panel) -> None:
        s0 = panel.px_close.iloc[:, 0]
        self._admit = bool(s0.iloc[-1] > 1.08 * s0.iloc[0])

    def target_weights(self, view) -> Slate:
        w = pd.Series(0.0, index=view.px_close.columns)
        w[view.px_close.columns[0]] = 0.5
        rank = pd.Series(np.nan, index=w.index, dtype=float)
        rank[view.px_close.columns[0]] = 1.0
        return Slate(weights=w, rank=rank, admit_new=self._admit)


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
    # Non-emptiness alone doesn't prove the book/state/equity branches fire — assert the
    # actual divergence, not just that *something* differed.
    assert any("resolved_book" in b for b in bad)
    assert any("state_at_signal" in b for b in bad)
    assert any("equity trajectory" in b for b in bad)


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


# ---------------------------------------------------------------- risk overlay

def _long_panel(make_panel, n=300, n_sym=4, seed=13) -> PanelView:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2025-01-05", periods=n, freq="B")
    cols = [f"S{i}" for i in range(n_sym)]
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, n_sym)), axis=0)),
                         index=dates, columns=cols)
    # one sector per name so the sector cap does not crush the book and pin k at 1.0
    return make_panel(close, gics_sector=pd.Series([f"G{i}" for i in range(n_sym)],
                                                   index=cols))


def test_closed_loop_passes_with_risk_overlay(make_panel):
    from number7.engine.schedule import weekly_rebalances
    from number7.risk.overlay import RiskConfig
    panel = _long_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    # a 3-name test book inherently breaches the 25% top-3 cap, which would crush the
    # book and saturate k at 1.0; loosening the concentration caps keeps the scalar
    # (the Σ-dependent channel this test exercises) live
    risk = RiskConfig(top3_cap=1.0, sector_cap=1.0)
    bad = closed_loop_violations(lambda p: RandomTopN(n=3, seed=9), panel, rb,
                                 CostModel(), sizing=cfg, risk_cfg=risk)
    assert bad == []


def test_closed_loop_catches_unmasked_sigma(make_panel, monkeypatch):
    """Overlay analogue of LookaheadTrap: a context built from the END of the run's own
    data (the classic end-of-data leak - unmasked Σ) must be caught by
    truncate-and-compare (risk spec §8 Causality). The leak must run to the end of EACH
    run's data, exactly like LookaheadTrap's stored panel: the full run then sees future
    the truncated run cannot reproduce, and the overlap diverges."""
    import number7.engine.backtest as bt
    from number7.engine.schedule import weekly_rebalances
    from number7.risk.overlay import RiskConfig, build_risk_context
    panel = _long_panel(make_panel)
    rb = weekly_rebalances(panel.sessions)
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    real_run = bt.run_backtest

    def run_with_leak(strategy, run_panel, *a, **kw):
        monkeypatch.setattr(
            bt, "build_risk_context",
            lambda view, *a2, **k2: build_risk_context(run_panel, *a2, **k2))
        return real_run(strategy, run_panel, *a, **kw)

    monkeypatch.setattr("number7.validation.causality.run_backtest", run_with_leak)
    risk = RiskConfig(top3_cap=1.0, sector_cap=1.0)   # keep the scalar live (see above)
    bad = closed_loop_violations(lambda p: RandomTopN(n=3, seed=9), panel, rb,
                                 CostModel(), sizing=cfg, risk_cfg=risk)
    assert bad != []
