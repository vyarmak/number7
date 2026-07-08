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
    buys: list[tuple[int, str, date, float]] = field(default_factory=list)
    _next_buy_id: int = 0

    @staticmethod
    def _check_event(qty: float, price: float) -> None:
        import math
        if not (math.isfinite(qty) and math.isfinite(price)) or qty <= 0 or price <= 0:
            raise ValueError(f"invalid trade event: qty={qty}, price={price} "
                             "(must be positive and finite)")

    def buy(self, symbol: str, d: date, qty: float, price: float) -> None:
        self._check_event(qty, price)
        buy_id = self._next_buy_id
        self._next_buy_id += 1
        self.open_lots.setdefault(symbol, []).append(
            Lot(symbol, d, qty, qty * price, buy_id=buy_id))
        self.buys.append((buy_id, symbol, d, qty))

    def _held_qty_at(self, buy_id: int, bought_qty: float, asof: date) -> float:
        """Shares from the lot opened by `buy_id` still held on `asof`."""
        realized_before = sum(r.qty for r in self.realized
                              if r.buy_id == buy_id and r.close_date <= asof)
        return max(bought_qty - realized_before, 0.0)

    def sell(self, symbol: str, d: date, qty: float, price: float) -> list[RealizedLot]:
        self._check_event(qty, price)
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
        """Each buy event's shares can serve as replacement for AT MOST their own
        quantity across all losses (global capacity), processed in loss-date order."""
        capacity = {buy_id: qty for buy_id, _, _, qty in self.buys}
        out = []
        losses = sorted((r for r in self.realized if r.pnl < 0), key=lambda r: r.close_date)
        for r in losses:
            matched, first_bd = 0.0, None
            for buy_id, sym, bd, qty in self.buys:
                if sym != r.symbol or buy_id == r.buy_id \
                        or abs((bd - r.close_date).days) > window_days:
                    continue
                # Pre-loss buys are replacements only if still held ON the loss date
                # (an already-exited position can't absorb the basis). Post-loss buys
                # count regardless of later sells - the wash occurred; the disallowed
                # loss defers into their basis and chains on a subsequent sale.
                structural = qty if bd >= r.close_date \
                    else self._held_qty_at(buy_id, qty, r.close_date)
                avail = min(structural, capacity.get(buy_id, 0.0))
                take = min(avail, r.qty - matched)
                if take <= 1e-12:
                    continue
                capacity[buy_id] -= take
                matched += take
                first_bd = bd if first_bd is None else min(first_bd, bd)
                if matched >= r.qty - 1e-12:
                    break
            if matched > 1e-12:
                out.append({"symbol": r.symbol, "loss_date": r.close_date,
                            "repurchase_date": first_bd,
                            "disallowed_loss": -r.pnl * matched / r.qty})
        return out

    def blackout_until(self, symbol: str, window_days: int = 30) -> date | None:
        losses = [r.close_date for r in self.realized if r.symbol == symbol and r.pnl < 0]
        return (max(losses) + timedelta(days=window_days)) if losses else None
