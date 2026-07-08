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


def test_same_day_second_lot_triggers_wash_on_loss():
    book = LotBook()
    book.buy("ABC", date(2026, 1, 5), 10, 100.0)   # lot A
    book.buy("ABC", date(2026, 1, 5), 10, 101.0)   # lot B, same day, distinct event
    book.sell("ABC", date(2026, 1, 20), 10, 90.0)  # FIFO: lot A realized at a loss
    ws = book.wash_sales()
    assert len(ws) == 1                            # lot B's purchase is a replacement buy
    assert ws[0]["repurchase_date"] == date(2026, 1, 5)


def test_fully_closed_prior_buy_is_not_a_replacement():
    book = LotBook()
    book.buy("DEF", date(2026, 1, 5), 10, 100.0)    # lot A
    book.sell("DEF", date(2026, 1, 10), 10, 105.0)  # lot A fully closed, at a gain
    book.buy("DEF", date(2026, 1, 12), 10, 110.0)   # lot B
    book.sell("DEF", date(2026, 1, 25), 10, 95.0)   # lot B realized at a loss
    # Lot A's buy is within ±30d of the loss but was fully closed before it —
    # nothing held to absorb the disallowed loss, so no wash sale.
    assert book.wash_sales() == []


def test_partial_replacement_disallows_proportionally():
    book = LotBook()
    book.buy("GHI", date(2026, 1, 5), 10, 100.0)
    book.sell("GHI", date(2026, 2, 2), 10, 90.0)   # loss of $100 on 10 shares
    book.buy("GHI", date(2026, 2, 10), 4, 92.0)    # replaces only 4 of 10 shares
    ws = book.wash_sales()
    assert len(ws) == 1
    assert ws[0]["disallowed_loss"] == pytest.approx(40.0)   # 4/10 of the $100 loss


def test_replacement_capacity_not_double_counted_across_losses():
    book = LotBook()
    book.buy("JKL", date(2026, 1, 5), 10, 100.0)    # lot A
    book.buy("JKL", date(2026, 1, 6), 10, 100.0)    # lot B
    book.buy("JKL", date(2026, 1, 20), 10, 95.0)    # lot C: the only replacement buy
    book.sell("JKL", date(2026, 1, 25), 10, 90.0)   # loss 1 (lot A, -$100)
    book.sell("JKL", date(2026, 1, 26), 10, 90.0)   # loss 2 (lot B, -$100)
    ws = book.wash_sales()
    # Lot C's 10 shares can absorb only ONE loss-worth of replacement in total
    assert sum(w["disallowed_loss"] for w in ws) == pytest.approx(100.0)
