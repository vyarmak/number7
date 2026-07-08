from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from number7.data.snapshot import SnapshotPaths

PRICE_COLS = ["symbol", "date", "open", "high", "low", "close", "volume", "unadjusted_close"]


def load_price_panel(snapshot_root: Path, symbols: list[str] | None = None,
                     start: str | None = None, end: str | None = None) -> pd.DataFrame:
    df = pd.read_parquet(SnapshotPaths(snapshot_root).prices)
    df["date"] = pd.to_datetime(df["date"])
    if symbols is not None:
        df = df[df["symbol"].isin(symbols)]
    if start is not None:
        df = df[df["date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["date"] <= pd.Timestamp(end)]
    return df.sort_values(["symbol", "date"], ignore_index=True)[PRICE_COLS]


def close_matrix(panel: pd.DataFrame) -> pd.DataFrame:
    return panel.pivot(index="date", columns="symbol", values="close").sort_index()


def connect_catalog(snapshot_root: Path) -> duckdb.DuckDBPyConnection:
    p = SnapshotPaths(snapshot_root)
    con = duckdb.connect()
    con.sql(f"create view prices as select * from read_parquet('{p.prices}')")
    con.sql(f"create view membership as select * from read_parquet('{p.membership}')")
    con.sql(f"create view metadata as select * from read_parquet('{p.metadata}')")
    return con
