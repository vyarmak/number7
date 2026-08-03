from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from number7.data.snapshot import SnapshotMeta, SnapshotPaths

SESSIONS = [date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1), date(2026, 7, 2)]


def _bars(symbol: str, days: list[date], px: float) -> pd.DataFrame:
    return pd.DataFrame({
        "symbol": symbol,
        "date": pd.to_datetime(days),
        "px_open": px, "px_high": px * 1.01, "px_low": px * 0.99, "px_close": px,
        "tr_open": px * 1.02, "tr_high": px * 1.03, "tr_low": px * 1.01,
        "tr_close": px * 1.02,
        "raw_close": px * 0.98, "volume": 1_000_000,
    })


@pytest.fixture
def fake_snapshot(tmp_path: Path) -> Path:
    root = tmp_path / "snapshots" / "2026-07-02"
    root.mkdir(parents=True)
    p = SnapshotPaths(root)
    prices = pd.concat([
        _bars("AAPL", SESSIONS, 200.0),
        _bars("ATVI", SESSIONS[:2], 95.0),          # stops trading 2026-06-30
        _bars("SPY", SESSIONS, 550.0),
    ], ignore_index=True)
    prices.to_parquet(p.prices, index=False)
    pd.DataFrame([
        {"symbol": "AAPL", "assetid": 1, "start": "2004-01-01", "end": None},
        {"symbol": "ATVI", "assetid": 2, "start": "2015-08-31", "end": "2026-06-30"},
    ]).to_parquet(p.membership, index=False)
    pd.DataFrame([
        {"symbol": "AAPL", "assetid": 1, "security_name": "Apple",
         "gics_sector": "Information Technology", "first_quoted_date": "1980-12-12",
         "last_quoted_date": None, "status": "active", "delisting_reason": None},
        {"symbol": "ATVI", "assetid": 2, "security_name": "Activision",
         "gics_sector": "Communication Services", "first_quoted_date": "1993-10-25",
         "last_quoted_date": "2026-06-30", "status": "delisted",
         "delisting_reason": "acquisition"},
        {"symbol": "SPY", "assetid": 3, "security_name": "SPDR S&P 500", "gics_sector": None,
         "first_quoted_date": "1993-01-29", "last_quoted_date": None, "status": "active",
         "delisting_reason": None},
    ]).to_parquet(p.metadata, index=False)
    meta = SnapshotMeta(db_date=date(2026, 7, 2), created_at=datetime.now(timezone.utc),
                        history_start=date(2004, 1, 1), watchlist="S&P 500 Current & Past",
                        n_symbols=3, n_price_rows=len(prices),
                        bases=["totalreturn", "capital"], file_sha256={})
    p.meta.write_text(meta.model_dump_json(indent=2))
    return root
