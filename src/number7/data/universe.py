from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from number7.data.snapshot import SnapshotPaths


def load_membership(snapshot_root: Path) -> pd.DataFrame:
    df = pd.read_parquet(SnapshotPaths(snapshot_root).membership)
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])  # None -> NaT (open interval)
    return df


def _covering(m: pd.DataFrame, ts: pd.Timestamp) -> pd.Series:
    return (m["start"] <= ts) & (m["end"].isna() | (ts <= m["end"]))  # end inclusive


def members_asof(membership: pd.DataFrame, d: date) -> set[str]:
    ts = pd.Timestamp(d)
    return set(membership.loc[_covering(membership, ts), "symbol"])


def member_union(membership: pd.DataFrame, start: date, end: date) -> set[str]:
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    overlap = (membership["start"] <= e) & (membership["end"].isna() | (membership["end"] >= s))
    return set(membership.loc[overlap, "symbol"])


def in_index_flags(membership: pd.DataFrame, symbols: list[str],
                   sessions: pd.DatetimeIndex) -> pd.DataFrame:
    out = pd.DataFrame(False, index=sessions, columns=list(symbols))
    for _, row in membership.iterrows():
        if row["symbol"] not in out.columns:
            continue
        end = row["end"] if pd.notna(row["end"]) else sessions[-1]
        mask = (sessions >= row["start"]) & (sessions <= end)
        out.loc[mask, row["symbol"]] = True
    return out
