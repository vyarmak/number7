import numpy as np
import pandas as pd

from number7.engine.backtest import run_backtest
from number7.engine.costs import CostModel
from number7.engine.schedule import weekly_rebalances
from number7.engine.strategy import Slate, StrategyManifest
from number7.research.ablate_risk_overlay import (_report, applied_k_stress_paths,
                                                  bind_rates, realized_vol_path)
from number7.risk.overlay import RiskConfig
from number7.strategies.sizing import SizingConfig


class FourEqual:
    manifest = StrategyManifest(name="four", family="test", origin="human", params={})

    def target_weights(self, view) -> Slate:
        cols = view.px_close.columns
        return Slate(weights=pd.Series(0.25, index=cols),
                     rank=pd.Series(np.arange(1.0, len(cols) + 1.0), index=cols),
                     admit_new=True)


def _results(make_panel):
    rng = np.random.default_rng(5)
    idx = pd.date_range("2025-01-05", periods=300, freq="B")
    cols = ["A", "B", "C", "D"]
    close = pd.DataFrame(
        100.0 * np.exp(np.cumsum(rng.normal(0.0002, 0.02, (300, 4)), axis=0)),
        index=idx, columns=cols)
    panel = make_panel(close, gics_sector=pd.Series([f"G{i}" for i in range(4)],
                                                    index=cols))
    rb = weekly_rebalances(panel.sessions)[-8:]
    cfg = SizingConfig(sleeve_equity=50_000.0, position_cap=0.30,
                       min_position_dollars=0.0)
    on = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                      initial=50_000.0, risk_cfg=RiskConfig())
    off = run_backtest(FourEqual(), panel, rb, CostModel(), sizing=cfg,
                       initial=50_000.0)
    return on, off


def test_report_contains_required_sections(make_panel):
    on, off = _results(make_panel)
    text = _report(on, off, monkey={"dd_pctile": 0.4}, snapshot="s", code_sha="c")
    for heading in ("## Headline cost/benefit", "## Monkey drawdown",
                    "## Realized vol vs target", "## Cap bind rates",
                    "## applied_k path"):
        assert heading in text
    assert "ADV no-binds at $50k are expected" in text
    assert "2016/2018 GICS boundaries" in text


def test_bind_rates_read_the_recorded_diagnostics(make_panel):
    on, _ = _results(make_panel)
    rates = bind_rates(on)
    assert rates["n"] == len(on.rebalance_dates)
    assert 0.0 <= rates["top3_bind_rate"] <= 1.0
    assert 0.0 <= rates["top3_without_sector_rate"] <= 1.0


def test_realized_vol_and_k_paths_have_expected_shape(make_panel):
    on, _ = _results(make_panel)
    rv = realized_vol_path(on, window=10).dropna()
    assert (rv >= 0).all()
    paths = applied_k_stress_paths(on)
    assert set(paths) == {"2008", "2020", "2022"}
    assert all(p["n"] == 0 for p in paths.values())   # 2025 fixture: outside windows
