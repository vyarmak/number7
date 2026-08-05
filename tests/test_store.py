import pandas as pd

from number7.data.store import close_matrix, connect_catalog, load_price_panel


def test_load_price_panel_filters(fake_snapshot):
    panel = load_price_panel(fake_snapshot, symbols=["AAPL"], start="2026-06-30")
    assert set(panel["symbol"]) == {"AAPL"}
    assert panel["date"].min() == pd.Timestamp("2026-06-30")
    assert list(panel.columns) == ["symbol", "date", "px_open", "px_high", "px_low",
                                   "px_close", "tr_open", "tr_high", "tr_low",
                                   "tr_close", "raw_close", "volume"]


def test_close_matrix_defaults_to_total_return(fake_snapshot):
    tidy = load_price_panel(fake_snapshot)
    tr = close_matrix(tidy)
    px = close_matrix(tidy, col="px_close")
    assert list(tr.columns) == ["AAPL", "ATVI", "SPY"]
    assert tr.index.is_monotonic_increasing
    assert pd.isna(tr.loc["2026-07-01", "ATVI"])
    assert tr.loc["2026-06-29", "AAPL"] > px.loc["2026-06-29", "AAPL"]


def test_catalog_sql(fake_snapshot):
    con = connect_catalog(fake_snapshot)
    n = con.sql("select count(*) from prices where symbol='SPY'").fetchone()[0]
    assert n == 4
    assert con.sql("select count(*) from membership").fetchone()[0] == 2
