from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from number7.config import Settings
from number7.data.bridge import BridgeHealth, fetch_health, make_client
from number7.data.snapshot import SnapshotMeta, SnapshotPaths, snapshot_dir, write_meta
from number7.data.store import BASES, PRICE_COLS

_OHLC = ("open", "high", "low", "close")


class SnapshotExistsError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _pull_basis(client, sym: str, start: str, adjustment: str) -> pd.DataFrame | None:
    df = client.price_timeseries(sym, start=start, adjustment=adjustment)
    if df.empty:
        return None
    prefix = BASES[adjustment]
    out = df[["date", *_OHLC, "unadjusted_close", "volume"]].copy()
    return out.rename(columns={c: f"{prefix}_{c}" for c in _OHLC})


def _pull_symbol(client, sym: str, start: str) -> pd.DataFrame | None:
    """Both bases for one symbol, merged on the session grid. A symbol that is empty in
    ONE basis but not the other is a bridge fault, not a pre-history delisting."""
    frames = {a: _pull_basis(client, sym, start, a) for a in BASES}
    present = [a for a, d in frames.items() if d is not None]
    if not present:
        return None
    if len(present) != len(BASES):
        raise RuntimeError(f"{sym}: bases {present} returned data but "
                           f"{sorted(set(BASES) - set(present))} did not")
    tr, px = frames["totalreturn"], frames["capital"]
    m = tr.merge(px.drop(columns=["volume"]), on="date", how="inner",
                 suffixes=("", "_px"))
    if not (len(m) == len(tr) == len(px)):
        raise RuntimeError(f"{sym}: totalreturn/capital session grids disagree "
                           f"({len(tr)} vs {len(px)} bars, {len(m)} common)")
    if not np.allclose(m["unadjusted_close"], m["unadjusted_close_px"],
                       rtol=1e-9, atol=1e-12):
        raise RuntimeError(f"{sym}: raw close differs between adjustment bases - "
                           "the bridge is not honouring the adjustment parameter")
    m = m.rename(columns={"unadjusted_close": "raw_close"}) \
         .drop(columns=["unadjusted_close_px"])
    m["symbol"] = sym
    return m[PRICE_COLS]


def _pull_prices(client, symbols: list[str], start: str,
                 required: set[str] = frozenset()) -> tuple[pd.DataFrame, list[str]]:
    """Pull per-symbol history in BOTH bases. A symbol may legitimately return no bars in
    range (delisted before `start` — the Current & Past watchlist reaches decades back),
    so empties are tolerated and reported — EXCEPT `required` symbols (e.g. SPY),
    whose absence is a hard failure."""
    frames, empty = [], []
    for sym in symbols:
        df = _pull_symbol(client, sym, start)
        if df is None:
            if sym in required:
                raise RuntimeError(f"bridge returned no data for required symbol {sym}")
            empty.append(sym)
            continue
        frames.append(df)
    if not frames:
        raise RuntimeError(f"bridge returned no price data for any of {len(symbols)} symbols "
                           "(outage, auth failure, or misconfigured watchlist?)")
    return pd.concat(frames, ignore_index=True), empty


def _flatten_membership(raw: list[dict]) -> pd.DataFrame:
    rows = [{"symbol": e["symbol"], "assetid": e["assetid"],
             "start": iv["start"], "end": iv["end"]}
            for e in raw for iv in e["intervals"]]
    df = pd.DataFrame(rows, columns=["symbol", "assetid", "start", "end"])
    df["start"] = pd.to_datetime(df["start"])   # proper types in parquet/DuckDB,
    df["end"] = pd.to_datetime(df["end"])       # not VARCHAR ISO strings
    return df


def run_sync(settings: Settings, client=None, health: BridgeHealth | None = None) -> Path:
    health = health or fetch_health(settings)
    client = client or make_client(settings)

    root = snapshot_dir(settings, health.db_date)
    paths = SnapshotPaths(root)
    if paths.meta.exists():
        raise SnapshotExistsError(f"snapshot {health.db_date} already finalized")
    root.mkdir(parents=True, exist_ok=True)

    symbols = sorted(set(client.watchlist_symbols(settings.watchlist)) | set(settings.extra_symbols))
    prices, empty_symbols = _pull_prices(client, symbols,
                                         start=settings.history_start.isoformat(),
                                         required=set(settings.extra_symbols))
    prices["date"] = pd.to_datetime(prices["date"])
    prices.to_parquet(paths.prices, index=False)

    _flatten_membership(client.sp500_membership_intervals()).to_parquet(paths.membership,
                                                                        index=False)

    meta_rows = client.metadata_batch(symbols)
    pd.DataFrame([{"symbol": s, **(m or {})} for s, m in meta_rows.items()]) \
        .to_parquet(paths.metadata, index=False)

    write_meta(paths, SnapshotMeta(
        db_date=health.db_date, created_at=datetime.now(timezone.utc),
        history_start=settings.history_start, watchlist=settings.watchlist,
        n_symbols=len(symbols), n_price_rows=len(prices),
        n_empty_symbols=len(empty_symbols), bases=list(BASES),
        file_sha256={p.name: _sha256(p) for p in (paths.prices, paths.membership,
                                                  paths.metadata)},
    ))
    return root
