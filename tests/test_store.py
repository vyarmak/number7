import pandas as pd

from number7.data.store import close_matrix, connect_catalog, load_price_panel


def test_load_price_panel_filters(fake_snapshot):
    panel = load_price_panel(fake_snapshot, symbols=["AAPL"], start="2026-06-30")
    assert set(panel["symbol"]) == {"AAPL"}
    assert panel["date"].min() == pd.Timestamp("2026-06-30")
    assert list(panel.columns) == ["symbol", "date", "open", "high", "low", "close",
                                   "volume", "unadjusted_close"]


def test_close_matrix_shape(fake_snapshot):
    m = close_matrix(load_price_panel(fake_snapshot))
    assert list(m.columns) == ["AAPL", "ATVI", "SPY"]
    assert m.index.is_monotonic_increasing
    assert pd.isna(m.loc["2026-07-01", "ATVI"])


def test_catalog_sql(fake_snapshot):
    con = connect_catalog(fake_snapshot)
    n = con.sql("select count(*) from prices where symbol='SPY'").fetchone()[0]
    assert n == 4
    assert con.sql("select count(*) from membership").fetchone()[0] == 2
