import numpy as np
import pandas as pd

from number7.engine.live import build_panel
from number7.engine.strategy import LookaheadTrap, PanelView, RandomTopN
from number7.validation.causality import causality_violations


def _walk_panel(n=10, n_sym=4, seed=13) -> PanelView:
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2026-06-01", periods=n, freq="B")
    close = pd.DataFrame(100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, n_sym)), axis=0)),
                         index=dates, columns=[f"S{i}" for i in range(n_sym)])
    ones = pd.DataFrame(True, index=dates, columns=close.columns)
    return PanelView(close=close, volume=close * 0 + 1e9,
                     unadjusted_close=close, in_index=ones)


def test_causal_strategy_is_clean(fake_snapshot):
    panel = build_panel(fake_snapshot)
    rb = pd.DatetimeIndex([panel.close.index[1], panel.close.index[2]])
    v = causality_violations(lambda p: RandomTopN(n=1, seed=5), panel, rb,
                             truncate_last_n=1)
    assert v == []


def test_lookahead_trap_is_caught():
    panel = _walk_panel()
    rb = pd.DatetimeIndex([panel.close.index[3], panel.close.index[5]])
    v = causality_violations(lambda p: LookaheadTrap(n=1, full_close=p.close),
                             panel, rb, truncate_last_n=3)
    assert len(v) >= 1
