from datetime import date

import pandas as pd

from number7.data.universe import in_index_flags, load_membership, member_union, members_asof


def test_membership_asof_and_union(fake_snapshot):
    m = load_membership(fake_snapshot)
    assert members_asof(m, date(2026, 6, 30)) == {"AAPL", "ATVI"}
    assert members_asof(m, date(2026, 7, 1)) == {"AAPL"}
    assert member_union(m, date(2026, 6, 1), date(2026, 7, 2)) == {"AAPL", "ATVI"}


def test_multiple_stints():
    m = pd.DataFrame({
        "symbol": ["X", "X"], "assetid": [1, 1],
        "start": pd.to_datetime(["1991-07-01", "2000-01-01"]),
        "end": pd.to_datetime(["1995-01-01", pd.NaT]),
    })
    assert members_asof(m, date(1993, 1, 1)) == {"X"}
    assert members_asof(m, date(1997, 1, 1)) == set()
    assert members_asof(m, date(2026, 1, 1)) == {"X"}


def test_in_index_flags(fake_snapshot):
    m = load_membership(fake_snapshot)
    sessions = pd.to_datetime(["2026-06-30", "2026-07-01"])
    flags = in_index_flags(m, ["AAPL", "ATVI"], sessions)
    assert flags.loc[sessions[0], "ATVI"] and not flags.loc[sessions[1], "ATVI"]
    assert flags["AAPL"].all()
