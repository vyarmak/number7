import numpy as np
import pandas as pd
import pytest

from number7.engine.costs import CostModel
from number7.engine.strategy import PanelView, StrategyManifest
from number7.validation.walkforward import WFProtocol, walk_forward


class AlwaysLong:
    manifest = StrategyManifest(name="long", family="test", origin="human", params={})

    def target_weights(self, view):
        w = pd.Series(0.0, index=view.close.columns)
        w[view.close.columns[0]] = 1.0
        return w


def _drift_panel(years=8, mu=0.0004):
    n = int(252 * years)
    dates = pd.date_range("2016-01-04", periods=n, freq="B")
    close = pd.DataFrame({"A": 100 * np.exp(np.cumsum(np.full(n, mu)))}, index=dates)
    ones = pd.DataFrame(True, index=dates, columns=["A"])
    return PanelView(close=close, volume=close * 0 + 1e9, unadjusted_close=close,
                     in_index=ones)


def test_walk_forward_on_steady_drift():
    protocol = WFProtocol(train_years=3, test_months=6, step_months=6, min_windows=8)
    report = walk_forward(lambda: AlwaysLong(), _drift_panel(), protocol,
                          CostModel(min_half_spread_bps=0.0))
    assert len(report.windows) >= 8
    assert report.wfe == pytest.approx(1.0, abs=0.15)      # same drift IS and OOS
    assert report.passes(protocol)
