from datetime import date

import httpx
import pytest

from number7.config import Settings
from number7.data.bridge import BridgeHealth
from number7.data.qc import QCIssue
from number7.ops.nightly import NightlyResult, run_nightly, run_nightly_with_retry


def _settings(tmp_path):
    return Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path,
                    heartbeat_url="http://hc/ping")


def _health():
    return BridgeHealth(status="ok", norgatedata_version="1", db_date=date(2026, 7, 2))


def test_success_path_promotes_and_pings(tmp_path, fake_snapshot):
    pings, promoted = [], []
    r = run_nightly(_settings(tmp_path),
                    sync=lambda s, **kw: fake_snapshot,
                    qc=lambda root, expected_db_date=None: [],
                    promote_fn=lambda s, d: promoted.append(d),
                    health_fn=lambda s: _health(),
                    ping=lambda url: pings.append(url))
    assert r.synced and r.qc_ok and r.promoted
    assert promoted == [date(2026, 7, 2)] and pings == ["http://hc/ping"]


def test_retry_recovers_from_transient_connect_errors(tmp_path):
    calls, delays = [], []

    def flaky(settings):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("[Errno 65] No route to host")
        return NightlyResult(promoted=True)

    r = run_nightly_with_retry(_settings(tmp_path), sleep=delays.append, run=flaky)
    assert r.promoted and len(calls) == 3
    assert delays == [30.0, 60.0]          # doubling backoff


def test_retry_gives_up_after_last_attempt(tmp_path):
    def always_down(settings):
        raise httpx.ConnectError("[Errno 65] No route to host")

    delays = []
    with pytest.raises(httpx.ConnectError):
        run_nightly_with_retry(_settings(tmp_path), sleep=delays.append, run=always_down)
    assert delays == [30.0, 60.0]          # 3 attempts, 2 waits, then dead-man fires


def test_retry_does_not_mask_non_transient_errors(tmp_path):
    calls = []

    def broken(settings):
        calls.append(1)
        raise RuntimeError("bridge returned no data for required symbol SPY")

    with pytest.raises(RuntimeError):
        run_nightly_with_retry(_settings(tmp_path), sleep=lambda s: None, run=broken)
    assert len(calls) == 1                 # real failures propagate immediately


def test_qc_failure_blocks_promotion_and_ping(tmp_path, fake_snapshot):
    pings, promoted = [], []
    bad = [QCIssue(check="ohlc_sanity", severity="error", detail="x")]
    r = run_nightly(_settings(tmp_path),
                    sync=lambda s, **kw: fake_snapshot,
                    qc=lambda root, expected_db_date=None: bad,
                    promote_fn=lambda s, d: promoted.append(d),
                    health_fn=lambda s: _health(),
                    ping=lambda url: pings.append(url))
    assert r.synced and not r.qc_ok and not r.promoted
    assert promoted == [] and pings == []
