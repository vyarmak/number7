from datetime import date

import pytest

from number7.execution.lots import LotBook


def test_fifo_realization():
    book = LotBook()
    book.buy("AAPL", date(2026, 1, 5), 10, 100.0)
    book.buy("AAPL", date(2026, 2, 2), 10, 110.0)
    realized = book.sell("AAPL", date(2026, 3, 2), 15, 120.0)
    assert sum(r.qty for r in realized) == 15
    assert realized[0].basis == pytest.approx(1000.0)
    assert realized[1].qty == 5 and realized[1].basis == pytest.approx(550.0)
    assert sum(r.pnl for r in realized) == pytest.approx(15 * 120 - 1000 - 550)


def test_sell_exceeding_open_raises():
    book = LotBook()
    book.buy("AAPL", date(2026, 1, 5), 10, 100.0)
    with pytest.raises(ValueError):
        book.sell("AAPL", date(2026, 2, 2), 11, 100.0)


def test_wash_sale_detected_on_reentry_within_30d():
    book = LotBook()
    book.buy("XYZ", date(2026, 1, 5), 10, 100.0)
    book.sell("XYZ", date(2026, 2, 2), 10, 90.0)           # realized loss
    book.buy("XYZ", date(2026, 2, 20), 10, 92.0)           # re-entry 18 days later
    ws = book.wash_sales()
    assert len(ws) == 1
    assert ws[0]["symbol"] == "XYZ"
    assert ws[0]["disallowed_loss"] == pytest.approx(100.0)
    assert book.blackout_until("XYZ") == date(2026, 3, 4)  # loss date + 30d


def test_no_wash_sale_outside_window():
    book = LotBook()
    book.buy("XYZ", date(2026, 1, 5), 10, 100.0)
    book.sell("XYZ", date(2026, 2, 2), 10, 90.0)
    book.buy("XYZ", date(2026, 3, 20), 10, 92.0)           # 46 days later
    assert book.wash_sales() == []
