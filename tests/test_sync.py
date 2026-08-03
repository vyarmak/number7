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
        assert adjustment in ("totalreturn", "capital")
        days = SESSIONS if symbol != "ATVI" else SESSIONS[:2]
        scale = 1.0 if adjustment == "capital" else 1.05      # TR drifts above price
        return pd.DataFrame({"date": days, "open": 1.0 * scale, "high": 1.1 * scale,
                             "low": 0.9 * scale, "close": 1.0 * scale,
                             "volume": 100, "unadjusted_close": 0.98})

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
    assert list(prices.columns) == ["symbol", "date", "px_open", "px_high", "px_low",
                                    "px_close", "tr_open", "tr_high", "tr_low",
                                    "tr_close", "raw_close", "volume"]
    membership = pd.read_parquet(p.membership)
    assert membership.loc[membership.symbol == "ATVI", "end"].iloc[0] \
        == pd.Timestamp("2026-06-30")
    meta = read_meta(p)
    assert meta.db_date == date(2026, 7, 2)
    assert meta.n_symbols == 3
    assert set(meta.file_sha256) == {"prices.parquet", "membership.parquet", "metadata.parquet"}


def test_run_sync_refuses_finished_snapshot(tmp_path):
    s = _settings(tmp_path)
    run_sync(s, client=FakeClient(), health=_health())
    with pytest.raises(SnapshotExistsError):
        run_sync(s, client=FakeClient(), health=_health())


def test_run_sync_fails_clearly_when_bridge_returns_nothing(tmp_path):
    class EmptyClient(FakeClient):
        def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
            import pandas as pd
            return pd.DataFrame()

    with pytest.raises(RuntimeError, match="bridge returned no"):
        run_sync(_settings(tmp_path), client=EmptyClient(), health=_health())


def test_empty_required_symbol_hard_fails(tmp_path):
    class NoSpyClient(FakeClient):
        def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
            import pandas as pd
            if symbol == "SPY":
                return pd.DataFrame()
            return super().price_timeseries(symbol, start, end, adjustment)

    with pytest.raises(RuntimeError, match="required symbol SPY"):
        run_sync(_settings(tmp_path), client=NoSpyClient(), health=_health())


def test_empty_nonrequired_symbol_tolerated_and_counted(tmp_path):
    class NoAtviClient(FakeClient):
        def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
            import pandas as pd
            if symbol == "ATVI":
                return pd.DataFrame()
            return super().price_timeseries(symbol, start, end, adjustment)

    root = run_sync(_settings(tmp_path), client=NoAtviClient(), health=_health())
    assert read_meta(SnapshotPaths(root)).n_empty_symbols == 1


def test_run_sync_stores_both_bases(tmp_path):
    root = run_sync(_settings(tmp_path), client=FakeClient(), health=_health())
    prices = pd.read_parquet(SnapshotPaths(root).prices)
    assert list(prices.columns) == ["symbol", "date", "px_open", "px_high", "px_low",
                                    "px_close", "tr_open", "tr_high", "tr_low",
                                    "tr_close", "raw_close", "volume"]
    row = prices.iloc[0]
    assert row["px_close"] == pytest.approx(1.0)
    assert row["tr_close"] == pytest.approx(1.05)
    assert row["raw_close"] == pytest.approx(0.98)
    assert read_meta(SnapshotPaths(root)).bases == ["totalreturn", "capital"]


def test_raw_close_disagreement_between_bases_is_fatal(tmp_path):
    class SkewedClient(FakeClient):
        def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
            df = super().price_timeseries(symbol, start, end, adjustment)
            if adjustment == "capital":
                df["unadjusted_close"] = 0.97      # raw price must be basis-independent
            return df

    with pytest.raises(RuntimeError, match="raw close differs"):
        run_sync(_settings(tmp_path), client=SkewedClient(), health=_health())


def test_session_grid_disagreement_between_bases_is_fatal(tmp_path):
    class ShortCapClient(FakeClient):
        def price_timeseries(self, symbol, start=None, end=None, adjustment="totalreturn"):
            df = super().price_timeseries(symbol, start, end, adjustment)
            return df.iloc[:-1] if adjustment == "capital" else df

    with pytest.raises(RuntimeError, match="session grids disagree"):
        run_sync(_settings(tmp_path), client=ShortCapClient(), health=_health())
