"""Offline test for the probe's polling budget: an MOC order submitted at the
15:40-15:45 ET cutoff fills at the 16:00 close, ~20 minutes later. The poll
loop must survive that long (120 * 5s = 10 min did not)."""
from __future__ import annotations

from types import SimpleNamespace

import number7.brokers.alpaca_probe as probe_mod


class _FakeClient:
    """Order stays open for the first `fills_after` polls, then fills —
    mimics a 15:40 submission that fills at the 16:00 closing auction."""

    def __init__(self, *a, **kw):
        self.polls = 0

    def submit_order(self, req):
        return SimpleNamespace(id="oid-1", status="accepted")

    def get_order_by_id(self, oid):
        self.polls += 1
        if self.polls > 200:  # > 10 min of 5s polls, < 25 min
            return SimpleNamespace(status="filled", filled_at="2026-07-09T20:00:01Z",
                                   filled_avg_price="623.45")
        return SimpleNamespace(status="accepted", filled_at=None)


def test_probe_polls_through_the_close(monkeypatch):
    monkeypatch.setattr(probe_mod, "TradingClient", _FakeClient)
    monkeypatch.setattr(probe_mod.time, "sleep", lambda s: None)
    monkeypatch.setattr(probe_mod, "get_settings",
                        lambda: SimpleNamespace(alpaca_key_id="k", alpaca_secret="s"))
    r = probe_mod.run_probe()
    assert r["filled"], "poll window too short to see the 16:00 close fill"
    assert r["fill_price"] == 623.45
