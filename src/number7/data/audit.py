from __future__ import annotations

import json

import numpy as np
import pandas as pd

from number7.config import get_settings
from number7.data.bridge import make_client

# Known-answer fixtures (public corporate-action record):
SPLITS = [("AAPL", "2020-08-31", 4.0), ("NVDA", "2024-06-10", 10.0)]
DELISTED = ["ATVI", "TWTR", "SIVB"]           # acquisition, acquisition, failure
DIVIDEND_PAYER = "KO"


def _split_continuity(client, symbol: str, ex_date: str) -> bool:
    """Adjusted close must NOT jump ~1/ratio across the split ex-date."""
    df = client.price_timeseries(symbol, adjustment="totalreturn")
    df = df.set_index(pd.to_datetime(df["date"]))
    r = np.log(df["close"]).diff().loc[ex_date]
    return bool(abs(float(r)) < 0.20)          # a missed 4:1 adjustment shows as ~-139% log move


def _delisted_served(client, symbol: str) -> bool:
    df = client.price_timeseries(symbol, adjustment="totalreturn")
    meta = client.metadata(symbol)
    if df is None or len(df) == 0 or meta is None or meta.get("last_quoted_date") is None:
        return False
    return str(pd.to_datetime(df["date"]).max().date()) == meta["last_quoted_date"]


def _totalreturn_dominates(client, symbol: str) -> bool:
    """Total-return cumulative growth must exceed capital-only for a dividend payer."""
    tr = client.price_timeseries(symbol, start="2010-01-01", adjustment="totalreturn")
    cap = client.price_timeseries(symbol, start="2010-01-01", adjustment="capital")

    def growth(d: pd.DataFrame) -> float:
        return float(d["close"].iloc[-1] / d["close"].iloc[0])

    return growth(tr) > growth(cap)


def audit_report(client) -> dict:
    return {
        **{f"split_{s}_{d}": _split_continuity(client, s, d) for s, d, _ in SPLITS},
        **{f"delisted_{s}": _delisted_served(client, s) for s in DELISTED},
        f"totalreturn_{DIVIDEND_PAYER}": _totalreturn_dominates(client, DIVIDEND_PAYER),
    }


if __name__ == "__main__":
    print(json.dumps(audit_report(make_client(get_settings())), indent=2))
