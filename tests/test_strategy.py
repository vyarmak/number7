import numpy as np
import pandas as pd

from number7.engine.strategy import PanelView, RandomTopN, StrategyManifest


def _view() -> PanelView:
    dates = pd.date_range("2026-06-01", periods=10, freq="B")
    close = pd.DataFrame(np.linspace(100, 110, 10)[:, None] * [1, 2, 3],
                         index=dates, columns=["A", "B", "C"])
    flags = pd.DataFrame(True, index=dates, columns=["A", "B", "C"])
    flags.loc[:, "C"] = False                             # C not in index
    return PanelView(close=close, volume=close * 0 + 1e6,
                     unadjusted_close=close, in_index=flags)


def test_random_topn_weights_are_valid_and_seeded():
    v = _view()
    s1, s2 = RandomTopN(n=2, seed=7), RandomTopN(n=2, seed=7)
    w1, w2 = s1.target_weights(v), s2.target_weights(v)
    pd.testing.assert_series_equal(w1, w2)
    assert (w1 >= 0).all() and w1.sum() <= 1.0 + 1e-9
    assert "C" not in w1[w1 > 0].index


def test_masked_to_hides_future():
    v = _view()
    cut = v.close.index[4]
    m = v.masked_to(cut)
    assert m.view_end == cut and len(m.close) == 5


def test_manifest_roundtrip():
    m = StrategyManifest(name="rand", family="null", origin="human", params={"n": 2})
    assert m.reentry_blackout_days == 0
