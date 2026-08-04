import numpy as np
import pandas as pd

from number7.engine.live import build_panel
from number7.engine.strategy import LookaheadTrap, PanelView, RandomTopN
from number7.validation.causality import causality_violations


def _walk_panel(make_panel, n=10, n_sym=4, seed=13) -> PanelView:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-06-01", periods=n, freq="B")
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, n_sym)), axis=0)),
                         index=dates, columns=[f"S{i}" for i in range(n_sym)])
    return make_panel(close)


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
