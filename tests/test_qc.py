from datetime import date

import pandas as pd

from number7.data.qc import qc_passes, run_qc, write_qc_report
from number7.data.snapshot import SnapshotPaths


def test_clean_snapshot_passes(fake_snapshot):
    issues = run_qc(fake_snapshot, expected_db_date=date(2026, 7, 2))
    assert qc_passes(issues), [i.model_dump() for i in issues]


def test_ohlc_violation_fails(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "low"] = df.loc[0, "high"] + 1
    df.to_parquet(p.prices, index=False)
    issues = run_qc(fake_snapshot)
    assert not qc_passes(issues)
    assert any(i.check == "ohlc_sanity" for i in issues)


def test_stale_db_date_fails(fake_snapshot):
    issues = run_qc(fake_snapshot, expected_db_date=date(2026, 7, 3))
    assert any(i.check == "freshness" and i.severity == "error" for i in issues)


def test_membership_orphan_fails(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    m = pd.read_parquet(p.membership)
    m.loc[len(m)] = {"symbol": "GHOST", "assetid": 99, "start": "2020-01-01", "end": None}
    m.to_parquet(p.membership, index=False)
    issues = run_qc(fake_snapshot)
    assert any(i.check == "membership_orphans" for i in issues)


def test_report_written(fake_snapshot):
    issues = run_qc(fake_snapshot)
    write_qc_report(fake_snapshot, issues)
    assert SnapshotPaths(fake_snapshot).qc_report.exists()


def test_open_ended_interval_followed_by_stint_is_overlap(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    m = pd.read_parquet(p.membership)
    # AAPL already has an open-ended interval (end=None); add a later stint
    m.loc[len(m)] = {"symbol": "AAPL", "assetid": 1, "start": "2030-01-01", "end": None}
    m.to_parquet(p.membership, index=False)
    issues = run_qc(fake_snapshot)
    assert any(i.check == "membership_overlap" for i in issues)
