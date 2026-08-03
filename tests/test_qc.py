from datetime import date

import pandas as pd

from number7.data.qc import qc_passes, run_qc, write_qc_report
from number7.data.snapshot import SnapshotPaths, read_meta


def test_clean_snapshot_passes(fake_snapshot):
    issues = run_qc(fake_snapshot, expected_db_date=date(2026, 7, 2))
    assert qc_passes(issues), [i.model_dump() for i in issues]


def test_ohlc_violation_fails(fake_snapshot):            # UPDATED: px basis
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "px_low"] = df.loc[0, "px_high"] + 1
    df.to_parquet(p.prices, index=False)
    issues = run_qc(fake_snapshot)
    assert not qc_passes(issues)
    assert any(i.check == "ohlc_sanity" and "px" in i.detail for i in issues)


def test_tr_basis_is_also_ohlc_checked(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "tr_high"] = df.loc[0, "tr_low"] - 1
    df.to_parquet(p.prices, index=False)
    assert any(i.check == "ohlc_sanity" and "tr" in i.detail
               for i in run_qc(fake_snapshot))


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


def test_pre_history_membership_without_prices_is_not_an_orphan(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    m = pd.read_parquet(p.membership)
    # left the index in 1999, before history_start=2004 -> no bars by design
    m.loc[len(m)] = {"symbol": "OLDCO", "assetid": 77, "start": "1990-01-01",
                     "end": "1999-06-30"}
    m.to_parquet(p.membership, index=False)
    issues = run_qc(fake_snapshot)
    assert not any(i.check == "membership_orphans" for i in issues)


def test_history_older_than_calendar_default_bound(fake_snapshot):
    """exchange_calendars' XNYS defaults to sessions starting ~20y before today;
    bars from 2004 (history_start) must not crash the calendar-gap check with
    DateOutOfBounds, nor flag contiguous old sessions as gaps."""
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    jan04 = pd.to_datetime(["2004-01-02", "2004-01-05", "2004-01-06",
                            "2004-01-07", "2004-01-08", "2004-01-09"])  # real XNYS sessions
    old = pd.DataFrame({"symbol": "OLDCO", "date": jan04,
                        "px_open": 10.0, "px_high": 10.1, "px_low": 9.9, "px_close": 10.0,
                        "tr_open": 10.0, "tr_high": 10.1, "tr_low": 9.9, "tr_close": 10.0,
                        "raw_close": 10.0, "volume": 1_000_000})
    pd.concat([df, old], ignore_index=True).to_parquet(p.prices, index=False)
    issues = run_qc(fake_snapshot)
    assert not any(i.check == "calendar_gaps" and "OLDCO" in i.detail for i in issues)


def test_nan_ohlc_fails_qc(fake_snapshot):               # UPDATED: px basis
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    df.loc[0, "px_close"] = float("nan")
    df.to_parquet(p.prices, index=False)
    assert any(i.check == "ohlc_sanity" for i in run_qc(fake_snapshot))


def test_missing_basis_in_meta_fails(fake_snapshot):
    p = SnapshotPaths(fake_snapshot)
    meta = read_meta(p)
    meta.bases = ["totalreturn"]
    p.meta.write_text(meta.model_dump_json(indent=2))
    assert any(i.check == "bases_recorded" for i in run_qc(fake_snapshot))


def test_identical_bases_over_a_long_span_fails(fake_snapshot):
    """A bridge that ignores `adjustment` returns the same series twice; over a
    multi-year S&P pull the two bases cannot be identical everywhere."""
    p = SnapshotPaths(fake_snapshot)
    df = pd.read_parquet(p.prices)
    long_days = pd.bdate_range("2020-01-02", "2022-01-01")  # start on a real XNYS session,
    # not 2020-01-01 (New Year's holiday) -- that date is a pandas business day but not a
    # calendar session, and becomes the global prices min, which crashes the (unrelated,
    # pre-existing) calendar-gap check with DateOutOfBounds instead of a clean QCIssue.
    dup = pd.DataFrame({"symbol": "DUP", "date": long_days,
                        "px_open": 10.0, "px_high": 10.1, "px_low": 9.9, "px_close": 10.0,
                        "tr_open": 10.0, "tr_high": 10.1, "tr_low": 9.9, "tr_close": 10.0,
                        "raw_close": 10.0, "volume": 1_000_000})
    pd.concat([df, dup], ignore_index=True).to_parquet(p.prices, index=False)
    assert any(i.check == "bases_distinct" for i in run_qc(fake_snapshot))
