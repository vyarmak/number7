from datetime import date, timedelta

from number7.config import Settings
from number7.ops.prune import prune_snapshots


def test_prune_keeps_recent_weekly_and_current(tmp_path):
    s = Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path)
    today = date(2026, 7, 2)
    days = [today - timedelta(days=i) for i in range(0, 60)]
    for d in days:
        (s.snapshots_dir / d.isoformat()).mkdir(parents=True)
    s.current_link.symlink_to(s.snapshots_dir / days[45].isoformat())

    deleted = prune_snapshots(s, keep_daily=30, today=today)

    kept = {p.name for p in s.snapshots_dir.iterdir()}
    assert days[0].isoformat() in kept                       # recent kept
    assert days[45].isoformat() in kept                      # current never deleted
    mondays = {d.isoformat() for d in days if d.isoweekday() == 1}
    assert mondays <= kept                                   # weekly anchors kept
    assert all(p.name not in kept for p in deleted)
    assert len(deleted) > 0
