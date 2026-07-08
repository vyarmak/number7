import pytest

from number7.brokers.alpaca_probe import run_probe

pytestmark = pytest.mark.paper


def test_moc_order_accepted_and_filled_at_close():
    r = run_probe("SPY", 1)
    assert r["accepted"], r
    assert r["filled"], "MOC not filled on paper - Phase 2 paper parity is INVALID (blueprint §14)"
