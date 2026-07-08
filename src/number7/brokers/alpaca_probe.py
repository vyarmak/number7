from __future__ import annotations

import json
import time

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from number7.config import get_settings


def run_probe(symbol: str = "SPY", qty: int = 1) -> dict:
    """Blueprint Phase-1 gate (§14, Copilot finding): verify Alpaca PAPER accepts and
    fills MOC (`cls` TIF) orders at/near the official closing print BEFORE Phase 2
    paper trading depends on it. Run on a trading day before ~15:45 ET."""
    s = get_settings()
    if not s.alpaca_key_id or not s.alpaca_secret:
        raise RuntimeError("Alpaca paper credentials missing: set N7_ALPACA_KEY_ID and "
                           "N7_ALPACA_SECRET in .env (paper keys only in Phase 1)")
    client = TradingClient(s.alpaca_key_id, s.alpaca_secret, paper=True)
    order = client.submit_order(MarketOrderRequest(
        symbol=symbol, qty=qty, side=OrderSide.BUY, time_in_force=TimeInForce.CLS))
    terminal_bad = {"rejected", "canceled", "expired"}

    def _is_bad(status) -> bool:
        return str(status).split(".")[-1].lower() in terminal_bad

    accepted = not _is_bad(order.status)
    fill_price, fill_time, filled = None, None, False
    for _ in range(120):                       # poll up to ~10 min after the close
        o = client.get_order_by_id(order.id)
        if _is_bad(o.status):                  # terminal non-acceptance: stop polling
            accepted = False
            break
        if o.filled_at is not None:
            filled = True
            fill_price = float(o.filled_avg_price)
            fill_time = str(o.filled_at)
            break
        time.sleep(5)
    return {"accepted": accepted, "filled": filled, "fill_price": fill_price,
            "fill_time": fill_time, "order_id": str(order.id)}


if __name__ == "__main__":
    print(json.dumps(run_probe(), indent=2))
