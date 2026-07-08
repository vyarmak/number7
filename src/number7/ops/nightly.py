from __future__ import annotations

from datetime import date

import httpx
from pydantic import BaseModel

from number7.config import Settings
from number7.data.bridge import fetch_health
from number7.data.qc import qc_passes, run_qc, write_qc_report
from number7.data.snapshot import promote, snapshot_dir
from number7.data.sync import SnapshotExistsError, run_sync


class NightlyResult(BaseModel):
    db_date: date | None = None
    synced: bool = False
    qc_ok: bool = False
    promoted: bool = False
    skipped_reason: str | None = None


def _ping(url: str) -> None:
    httpx.get(url, timeout=10).raise_for_status()


def run_nightly(settings: Settings, *, sync=run_sync, qc=run_qc, promote_fn=promote,
                health_fn=fetch_health, ping=_ping) -> NightlyResult:
    r = NightlyResult()
    health = health_fn(settings)
    r.db_date = health.db_date
    try:
        root = sync(settings, health=health)
        r.synced = True
    except SnapshotExistsError:
        root = snapshot_dir(settings, health.db_date)
        r.synced, r.skipped_reason = True, "exists"

    issues = qc(root, expected_db_date=health.db_date)
    write_qc_report(root, issues)
    r.qc_ok = qc_passes(issues)
    if not r.qc_ok:
        return r                       # no promote, no ping -> dead-man fires

    promote_fn(settings, health.db_date)
    r.promoted = True
    if settings.heartbeat_url:
        ping(settings.heartbeat_url)
    return r


if __name__ == "__main__":
    from number7.config import get_settings
    from number7.ops.prune import prune_snapshots

    result = run_nightly(get_settings())
    prune_snapshots(get_settings())
    print(result.model_dump_json(indent=2))
    raise SystemExit(0 if result.promoted else 1)
