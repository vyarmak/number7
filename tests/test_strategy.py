import numpy as np
import pandas as pd

from number7.engine.strategy import RandomTopN, Slate, StrategyManifest, full_slate


def _view(make_panel):
    dates = pd.date_range("2026-06-01", periods=10, freq="B")
    close = pd.DataFrame(np.linspace(100, 110, 10)[:, None] * [1, 2, 3],
                         index=dates, columns=["A", "B", "C"])
    flags = pd.DataFrame(True, index=dates, columns=["A", "B", "C"])
    flags.loc[:, "C"] = False                             # C not in index
    return make_panel(close, in_index=flags)


def test_random_topn_emits_a_slate(make_panel):
    v = _view(make_panel)
    s1, s2 = RandomTopN(n=2, seed=7), RandomTopN(n=2, seed=7)
    a, b = s1.target_weights(v), s2.target_weights(v)
    assert isinstance(a, Slate) and a.admit_new is True
    pd.testing.assert_series_equal(a.weights, b.weights)
    assert (a.weights >= 0).all() and a.weights.sum() <= 1.0 + 1e-9
    assert "C" not in a.weights[a.weights > 0].index      # C is not a constituent
    held = a.weights[a.weights > 0].index
    assert a.rank.loc[held].notna().all()                 # every funded name is ranked
    assert a.rank.dropna().is_unique


def test_full_slate_ranks_by_descending_weight():
    w = pd.Series({"A": 0.2, "B": 0.5, "C": 0.0})
    s = full_slate(w)
    assert s.admit_new is True
    assert s.rank["B"] == 1.0 and s.rank["A"] == 2.0
    assert pd.isna(s.rank["C"])


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
