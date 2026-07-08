from datetime import date

from number7.config import Settings
from number7.data.bridge import BridgeHealth
from number7.data.qc import QCIssue
from number7.ops.nightly import run_nightly


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
