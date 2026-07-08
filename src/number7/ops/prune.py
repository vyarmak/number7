from __future__ import annotations

import shutil
from datetime import date, timedelta
from pathlib import Path

from number7.config import Settings


def prune_snapshots(settings: Settings, keep_daily: int = 30,
                    today: date | None = None) -> list[Path]:
    today = today or date.today()
    cutoff = today - timedelta(days=keep_daily)
    link = settings.current_link
    current = link.resolve() if link.is_symlink() else None   # resolve() is non-strict:
    # a broken symlink still yields its target path, so retention stays deterministic
    deleted: list[Path] = []
    if not settings.snapshots_dir.exists():
        return deleted
    for p in sorted(settings.snapshots_dir.iterdir()):
        if not p.is_dir() or p.is_symlink():
            continue
        try:
            d = date.fromisoformat(p.name)
        except ValueError:
            continue
        keep = (d >= cutoff) or (d.isoweekday() == 1) or (current is not None
                                                          and p.resolve() == current)
        if not keep:
            shutil.rmtree(p)
            deleted.append(p)
    return deleted
