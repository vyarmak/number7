from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel

from number7.config import Settings


class SnapshotMeta(BaseModel):
    db_date: date
    created_at: datetime
    history_start: date
    watchlist: str
    n_symbols: int
    n_price_rows: int
    bases: list[str]             # adjustments present, e.g. ["totalreturn", "capital"].
    # REQUIRED (no default) on purpose: a pre-dual-basis snapshot must be detectably
    # unusable for the momentum sleeve, never silently mis-ranked (spec §2).
    n_empty_symbols: int = 0     # requested symbols with no bars in range (pre-start delistings)
    file_sha256: dict[str, str]


@dataclass(frozen=True)
class SnapshotPaths:
    root: Path

    @property
    def prices(self) -> Path:
        return self.root / "prices.parquet"

    @property
    def membership(self) -> Path:
        return self.root / "membership.parquet"

    @property
    def metadata(self) -> Path:
        return self.root / "metadata.parquet"

    @property
    def meta(self) -> Path:
        return self.root / "meta.json"

    @property
    def qc_report(self) -> Path:
        return self.root / "qc_report.json"


def snapshot_dir(settings: Settings, db_date: date) -> Path:
    return settings.snapshots_dir / db_date.isoformat()


def write_meta(paths: SnapshotPaths, meta: SnapshotMeta) -> None:
    paths.meta.write_text(meta.model_dump_json(indent=2))


def read_meta(paths: SnapshotPaths) -> SnapshotMeta:
    return SnapshotMeta.model_validate_json(paths.meta.read_text())


def promote(settings: Settings, db_date: date) -> None:
    """Atomically point data/current at the snapshot (symlink swap via rename)."""
    target = snapshot_dir(settings, db_date)
    if not target.is_dir():
        raise FileNotFoundError(f"snapshot missing: {target}")
    link, tmp = settings.current_link, settings.current_link.with_name("current.tmp")
    tmp.unlink(missing_ok=True)
    tmp.symlink_to(target, target_is_directory=True)
    os.replace(tmp, link)


def current_snapshot(settings: Settings) -> Path | None:
    link = settings.current_link
    return link.resolve() if link.is_symlink() else None   # promote() manages a symlink;
    # anything else at data/current is misconfiguration and must not be silently accepted
