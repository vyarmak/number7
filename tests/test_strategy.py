import numpy as np
import pandas as pd

from number7.engine.strategy import RandomTopN, StrategyManifest


def _view(make_panel):
    dates = pd.date_range("2026-06-01", periods=10, freq="B")
    close = pd.DataFrame(np.linspace(100, 110, 10)[:, None] * [1, 2, 3],
                         index=dates, columns=["A", "B", "C"])
    flags = pd.DataFrame(True, index=dates, columns=["A", "B", "C"])
    flags.loc[:, "C"] = False                             # C not in index
    return make_panel(close, in_index=flags)


def test_random_topn_weights_are_valid_and_seeded(make_panel):
    v = _view(make_panel)
    s1, s2 = RandomTopN(n=2, seed=7), RandomTopN(n=2, seed=7)
    w1, w2 = s1.target_weights(v), s2.target_weights(v)
    pd.testing.assert_series_equal(w1, w2)
    assert (w1 >= 0).all() and w1.sum() <= 1.0 + 1e-9
    assert "C" not in w1[w1 > 0].index


def test_masked_to_hides_future_in_every_frame(make_panel):
    v = _view(make_panel)
    cut = v.sessions[4]
    m = v.masked_to(cut)
    assert m.view_end == cut
    for f in (m.px_open, m.px_high, m.px_low, m.px_close, m.tr_close,
              m.raw_close, m.volume, m.in_index):
        assert len(f) == 5 and f.index[-1] == cut
    pd.testing.assert_series_equal(m.assetid, v.assetid)   # not time-indexed


def test_manifest_roundtrip():
    m = StrategyManifest(name="rand", family="null", origin="human", params={"n": 2})
    assert m.reentry_blackout_days == 0


def test_validate_weights_rejects_shorts_and_leverage():
    import pytest
    from number7.engine.strategy import validate_weights
    with pytest.raises(ValueError, match="negative"):
        validate_weights(pd.Series({"A": -0.1, "B": 0.5}))
    with pytest.raises(ValueError, match="leverage"):
        validate_weights(pd.Series({"A": 0.8, "B": 0.5}))
    validate_weights(pd.Series({"A": 0.5, "B": 0.5}))   # exactly fully invested is fine


def test_validate_weights_rejects_non_finite():
    import pytest
    from number7.engine.strategy import validate_weights
    with pytest.raises(ValueError, match="non-finite"):
        validate_weights(pd.Series({"A": float("nan"), "B": 0.5}))
    with pytest.raises(ValueError, match="non-finite"):
        validate_weights(pd.Series({"A": float("inf")}))
