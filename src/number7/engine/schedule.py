from __future__ import annotations

import exchange_calendars as xcals
import pandas as pd


def sessions_between(start: str, end: str) -> pd.DatetimeIndex:
    return xcals.get_calendar("XNYS").sessions_in_range(start, end)


def weekly_rebalances(sessions: pd.DatetimeIndex, weekday: int = 1) -> pd.DatetimeIndex:
    """First session of each ISO week whose weekday >= `weekday` (Tuesday default).
    A holiday on the target weekday slides the rebalance to the next session that week."""
    iso = sessions.isocalendar()
    keys = (iso.year * 100 + iso.week).to_numpy()
    out: list[pd.Timestamp] = []
    for _, grp in pd.Series(sessions, index=sessions).groupby(keys):
        hits = [d for d in grp.index if d.weekday() >= weekday]
        if hits:
            out.append(hits[0])
    return pd.DatetimeIndex(out)


def signal_date(sessions: pd.DatetimeIndex, t: pd.Timestamp) -> pd.Timestamp:
    try:
        i = sessions.get_loc(t)
    except KeyError:
        raise ValueError(f"{t.date()} is not a session in the provided calendar") from None
    if i == 0:
        raise ValueError("no session before the first session")
    return sessions[i - 1]
