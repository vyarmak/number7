from datetime import date, datetime, timezone

from number7.config import Settings
from number7.data.snapshot import (SnapshotMeta, SnapshotPaths, current_snapshot,
                                   promote, read_meta, snapshot_dir, write_meta)


def _settings(tmp_path):
    return Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path)


def test_snapshot_paths_layout(tmp_path):
    p = SnapshotPaths(tmp_path)
    assert p.prices.name == "prices.parquet"
    assert p.membership.name == "membership.parquet"
    assert p.metadata.name == "metadata.parquet"
    assert p.meta.name == "meta.json"
    assert p.qc_report.name == "qc_report.json"


def test_meta_roundtrip(tmp_path):
    p = SnapshotPaths(tmp_path)
    meta = SnapshotMeta(db_date=date(2026, 7, 2), created_at=datetime.now(timezone.utc),
                        history_start=date(2004, 1, 1), watchlist="W", n_symbols=3,
                        n_price_rows=10, bases=["totalreturn", "capital"],
                        file_sha256={"prices.parquet": "ab"})
    write_meta(p, meta)
    assert read_meta(p).db_date == date(2026, 7, 2)


def test_promote_and_current(tmp_path, fake_snapshot):
    s = _settings(tmp_path)
    assert current_snapshot(s) is None
    promote(s, date(2026, 7, 2))
    cur = current_snapshot(s)
    assert cur is not None and cur.resolve() == fake_snapshot.resolve()
    promote(s, date(2026, 7, 2))
    assert current_snapshot(s).resolve() == fake_snapshot.resolve()


def test_snapshot_dir_layout(tmp_path):
    s = _settings(tmp_path)
    assert snapshot_dir(s, date(2026, 7, 2)) == tmp_path / "snapshots" / "2026-07-02"
