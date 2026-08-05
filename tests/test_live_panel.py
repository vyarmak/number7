import pytest

from number7.data.snapshot import SnapshotPaths, read_meta
from number7.engine.live import MissingBasisError, build_panel


def test_build_panel_carries_both_bases_and_assetids(fake_snapshot):
    panel = build_panel(fake_snapshot)
    assert list(panel.px_close.columns) == ["AAPL", "ATVI", "SPY"]
    assert panel.tr_close.loc["2026-06-29", "AAPL"] > panel.px_close.loc["2026-06-29", "AAPL"]
    assert panel.raw_close.loc["2026-06-29", "AAPL"] < panel.px_close.loc["2026-06-29", "AAPL"]
    assert panel.assetid["AAPL"] == 1.0


def test_regime_instrument_is_not_a_constituent(fake_snapshot):
    """Confirmed defect #1: build_panel used to force in_index=True for extra_symbols,
    making SPY a buyable candidate and polluting the hold_top_pct denominator."""
    panel = build_panel(fake_snapshot)
    assert not panel.in_index["SPY"].any()
    assert panel.in_index["AAPL"].all()


def test_snapshot_without_price_basis_is_rejected(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    meta = read_meta(p)
    meta.bases = ["totalreturn"]
    p.meta.write_text(meta.model_dump_json(indent=2))
    with pytest.raises(MissingBasisError, match="capital"):
        build_panel(fake_snapshot)
