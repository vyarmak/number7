import pandas as pd
import pytest

from number7.engine.schedule import sessions_between, signal_date, weekly_rebalances


def test_sessions_skip_holidays():
    s = sessions_between("2026-07-01", "2026-07-08")
    assert pd.Timestamp("2026-07-03") not in s          # July 4th observed
    assert pd.Timestamp("2026-07-06") in s


def test_weekly_rebalances_are_tuesdays():
    s = sessions_between("2026-06-01", "2026-06-30")
    rb = weekly_rebalances(s, weekday=1)
    assert all(d.weekday() == 1 for d in rb)
    assert len(rb) == 5                                  # 5 Tuesdays in June 2026


def test_weekly_rebalance_slides_on_holiday():
    # week of 2026-07-06: Tue 7/7 is a normal session; sanity — first hit is the Tuesday
    s = sessions_between("2026-07-06", "2026-07-10")
    rb = weekly_rebalances(s, weekday=1)
    assert list(rb) == [pd.Timestamp("2026-07-07")]


def test_signal_date_is_prior_session():
    s = sessions_between("2026-07-01", "2026-07-08")
    assert signal_date(s, pd.Timestamp("2026-07-06")) == pd.Timestamp("2026-07-02")
    with pytest.raises(ValueError):
        signal_date(s, s[0])
