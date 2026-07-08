from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Lot:
    symbol: str
    open_date: date
    qty: float
    basis: float          # total dollars paid for the remaining qty
    buy_id: int = -1      # id of the buy event that opened this lot


@dataclass
class RealizedLot:
    symbol: str
    open_date: date
    close_date: date
    qty: float
    proceeds: float
    basis: float
    buy_id: int = -1

    @property
    def pnl(self) -> float:
        return self.proceeds - self.basis


@dataclass
class LotBook:
    """FIFO lot accounting + wash-sale detection (blueprint §8 tax clause, coded in
    Phase 1 by review mandate §14). Buy events carry unique ids so a wash-sale check
    excludes only the sold lot's OWN opening purchase — two lots opened the same day
    are distinct events."""

    open_lots: dict[str, list[Lot]] = field(default_factory=dict)
    realized: list[RealizedLot] = field(default_factory=list)
    buys: list[tuple[int, str, date]] = field(default_factory=list)
    _next_buy_id: int = 0

    def buy(self, symbol: str, d: date, qty: float, price: float) -> None:
        buy_id = self._next_buy_id
        self._next_buy_id += 1
        self.open_lots.setdefault(symbol, []).append(
            Lot(symbol, d, qty, qty * price, buy_id=buy_id))
        self.buys.append((buy_id, symbol, d))

    def sell(self, symbol: str, d: date, qty: float, price: float) -> list[RealizedLot]:
        out: list[RealizedLot] = []
        remaining = qty
        lots = self.open_lots.get(symbol, [])
        while remaining > 1e-12 and lots:
            lot = lots[0]
            take = min(lot.qty, remaining)
            basis_part = lot.basis * (take / lot.qty)
            out.append(RealizedLot(symbol, lot.open_date, d, take, take * price,
                                   basis_part, buy_id=lot.buy_id))
            lot.qty -= take
            lot.basis -= basis_part
            remaining -= take
            if lot.qty <= 1e-12:
                lots.pop(0)
        if remaining > 1e-12:
            raise ValueError(f"sell exceeds open quantity for {symbol}")
        self.realized.extend(out)
        return out

    def wash_sales(self, window_days: int = 30) -> list[dict]:
        out = []
        for r in self.realized:
            if r.pnl >= 0:
                continue
            for buy_id, sym, bd in self.buys:
                if (sym == r.symbol and buy_id != r.buy_id
                        and abs((bd - r.close_date).days) <= window_days):
                    out.append({"symbol": r.symbol, "loss_date": r.close_date,
                                "repurchase_date": bd, "disallowed_loss": -r.pnl})
                    break
        return out

    def blackout_until(self, symbol: str, window_days: int = 30) -> date | None:
        losses = [r.close_date for r in self.realized if r.symbol == symbol and r.pnl < 0]
        return (max(losses) + timedelta(days=window_days)) if losses else None
