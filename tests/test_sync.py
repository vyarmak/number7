from datetime import date

import pandas as pd
import pytest

from number7.config import Settings
from number7.data.bridge import BridgeHealth
from number7.data.snapshot import SnapshotPaths, read_meta
from number7.data.sync import SnapshotExistsError, run_sync

SESSIONS = pd.to_datetime(["2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02"])


class FakeClient:
    def watchlist_symbols(self, name):
        assert name == "S&P 500 Current & Past"
        return ["AAPL", "ATVI"]

    def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
        assert adjustment == "totalreturn"
        days = SESSIONS if symbol != "ATVI" else SESSIONS[:2]
        return pd.DataFrame({"date": days, "open": 1.0, "high": 1.1, "low": 0.9,
                             "close": 1.0, "volume": 100, "unadjusted_close": 1.0})

    def sp500_membership_intervals(self):
        return [
            {"symbol": "AAPL", "assetid": 1, "intervals": [{"start": "2004-01-01", "end": None}]},
            {"symbol": "ATVI", "assetid": 2,
             "intervals": [{"start": "2015-08-31", "end": "2026-06-30"}]},
        ]

    def metadata_batch(self, symbols):
        return {s: {"assetid": i + 1, "security_name": s, "gics_sector": "X",
                    "first_quoted_date": "1990-01-01", "last_quoted_date": None,
                    "status": "active", "domicile": "US", "delisting_reason": None}
                for i, s in enumerate(symbols)}


def _settings(tmp_path):
    return Settings(norgate_base_url="http://x", norgate_token="t", data_dir=tmp_path)


def _health():
    return BridgeHealth(status="ok", norgatedata_version="1", db_date=date(2026, 7, 2))


def test_run_sync_builds_snapshot(tmp_path):
    root = run_sync(_settings(tmp_path), client=FakeClient(), health=_health())
    p = SnapshotPaths(root)
    prices = pd.read_parquet(p.prices)
    assert set(prices["symbol"].unique()) == {"AAPL", "ATVI", "SPY"}
    assert list(prices.columns) == ["symbol", "date", "open", "high", "low", "close",
                                    "volume", "unadjusted_close"]
    membership = pd.read_parquet(p.membership)
    assert membership.loc[membership.symbol == "ATVI", "end"].iloc[0] == "2026-06-30"
    meta = read_meta(p)
    assert meta.db_date == date(2026, 7, 2)
    assert meta.n_symbols == 3
    assert set(meta.file_sha256) == {"prices.parquet", "membership.parquet", "metadata.parquet"}


def test_run_sync_refuses_finished_snapshot(tmp_path):
    s = _settings(tmp_path)
    run_sync(s, client=FakeClient(), health=_health())
    with pytest.raises(SnapshotExistsError):
        run_sync(s, client=FakeClient(), health=_health())
