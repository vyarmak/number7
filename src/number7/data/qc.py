from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Literal

import exchange_calendars as xcals
import numpy as np
import pandas as pd
from pydantic import BaseModel

from number7.data.snapshot import SnapshotPaths, read_meta
from number7.data.store import PRICE_COLS, load_price_panel
from number7.data.universe import load_membership


class QCIssue(BaseModel):
    check: str
    severity: Literal["error", "warn"]
    detail: str


def _err(check: str, detail: str) -> QCIssue:
    return QCIssue(check=check, severity="error", detail=detail)


def _warn(check: str, detail: str) -> QCIssue:
    return QCIssue(check=check, severity="warn", detail=detail)


def run_qc(snapshot_root: Path, expected_db_date: date | None = None) -> list[QCIssue]:
    paths = SnapshotPaths(snapshot_root)
    issues: list[QCIssue] = []
    prices = load_price_panel(snapshot_root)
    membership = load_membership(snapshot_root)

    # 1. schema
    if list(prices.columns) != PRICE_COLS:
        issues.append(_err("schema", f"price columns {list(prices.columns)}"))
    if list(membership.columns) != ["symbol", "assetid", "start", "end"]:
        issues.append(_err("schema", f"membership columns {list(membership.columns)}"))

    # 2. ohlc sanity, PER BASIS (NaN comparisons are False, so missing prices must be
    # caught explicitly). Each basis is internally consistent or the snapshot is bad.
    for prefix in ("px", "tr"):
        o, h, low, c = (f"{prefix}_{x}" for x in ("open", "high", "low", "close"))
        ohlc = prices[[o, h, low, c]]
        bad = prices[(prices[low] > prices[[o, c]].min(axis=1))
                     | (prices[h] < prices[[o, c]].max(axis=1))
                     | (prices[low] > prices[h])
                     | (ohlc <= 0).any(axis=1)
                     | ohlc.isna().any(axis=1)]
        if len(bad):
            issues.append(_err("ohlc_sanity", f"{prefix}: {len(bad)} bad bars, first: "
                               f"{bad.iloc[0]['symbol']} {bad.iloc[0]['date'].date()}"))
    if (prices["raw_close"] <= 0).any() or prices["raw_close"].isna().any():
        issues.append(_err("ohlc_sanity", "raw_close: non-positive or missing values"))

    # 3. interior calendar gaps (SPY + 20 biggest symbols)
    # XNYS defaults to sessions from ~20y before today; our history reaches 2004,
    # so pin the calendar start to the data (cache is keyed on the kwargs).
    cal = xcals.get_calendar("XNYS", start=prices["date"].min())
    counts = prices.groupby("symbol").size().sort_values(ascending=False)
    check_syms = list(dict.fromkeys(["SPY", *counts.head(20).index]))
    for sym in check_syms:
        g = prices[prices["symbol"] == sym]
        if g.empty:
            continue
        expected = cal.sessions_in_range(g["date"].min(), g["date"].max())
        missing = expected.difference(pd.DatetimeIndex(g["date"]))
        if len(missing):
            issues.append(_err("calendar_gaps", f"{sym}: {len(missing)} interior sessions "
                               f"missing (first {missing[0].date()})"))

    # 4. outlier returns without an index move (P&L basis)
    close = prices.pivot(index="date", columns="symbol", values="tr_close").sort_index()
    rets = np.log(close).diff()
    if "SPY" in rets.columns and len(rets) > 2:
        spy_calm = rets["SPY"].abs() < 0.01
        std = rets.std(ddof=0).replace(0.0, np.nan)
        z = (rets - rets.mean()) / std
        flagged = z.abs().gt(4) & spy_calm.to_numpy()[:, None]
        n = int(flagged.fillna(False).to_numpy().sum())
        if n:
            issues.append(_warn("outliers", f"{n} >4-sigma returns on calm-SPY days"))

    # 5. overlapping intervals per assetid (an open-ended stint overlaps ANY later one)
    for aid, g in membership.sort_values("start").groupby("assetid"):
        prev_end: pd.Timestamp | None = None
        seen_first = False
        for _, row in g.iterrows():
            if seen_first and (pd.isna(prev_end) or row["start"] <= prev_end):
                issues.append(_err("membership_overlap", f"assetid {aid}"))
                break
            prev_end, seen_first = row["end"], True

    # 6. membership symbols without prices — only for stints overlapping the pulled
    # range (a constituent that left before history_start has no bars BY DESIGN;
    # sync counts those in meta.n_empty_symbols)
    hs = pd.Timestamp(read_meta(paths).history_start)
    active = membership[membership["end"].isna() | (membership["end"] >= hs)]
    orphans = set(active["symbol"]) - set(prices["symbol"])
    if orphans:
        issues.append(_err("membership_orphans", f"{sorted(orphans)[:5]}"))

    # 7. freshness
    if expected_db_date is not None:
        meta = read_meta(paths)
        if meta.db_date != expected_db_date:
            issues.append(_err("freshness",
                               f"db_date {meta.db_date} != expected {expected_db_date}"))

    # 8. row floor for full-history pulls
    span_years = (prices["date"].max() - prices["date"].min()).days / 365.25
    if span_years >= 15 and len(prices) < 500_000:
        issues.append(_err("row_floor", f"only {len(prices)} rows over {span_years:.1f}y"))

    # 9. metadata records the bases actually stored
    meta = read_meta(paths)
    missing = {"totalreturn", "capital"} - set(meta.bases)
    if missing:
        issues.append(_err("bases_recorded", f"meta.bases={meta.bases} missing {sorted(missing)}"))

    # 10. the two bases must actually differ somewhere. A bridge that silently ignores
    # `adjustment` returns the same series twice; over a multi-year pull of hundreds of
    # dividend payers, px_close == tr_close everywhere is impossible.
    if span_years >= 1 and bool((prices["px_close"] == prices["tr_close"]).all()):
        issues.append(_err("bases_distinct", "px_close == tr_close on every row over "
                           f"{span_years:.1f}y - the capital basis is not distinct"))

    return issues


def qc_passes(issues: list[QCIssue]) -> bool:
    return not any(i.severity == "error" for i in issues)


def write_qc_report(snapshot_root: Path, issues: list[QCIssue]) -> None:
    SnapshotPaths(snapshot_root).qc_report.write_text(
        json.dumps([i.model_dump() for i in issues], indent=2))
