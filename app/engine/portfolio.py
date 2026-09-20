import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Any

from app.models import PositionModel, PortfolioSnapshotModel
from app.db import db_session, SessionLocal

logger = logging.getLogger(__name__)


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float

    @property
    def market_value(self) -> float:
        return round(self.quantity * self.current_price, 4)

    @property
    def unrealized_pnl(self) -> float:
        if self.quantity <= 0:
            return 0.0
        return round((self.current_price - self.avg_entry_price) * self.quantity, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": round(self.quantity, 4),
            "avg_entry_price": round(self.avg_entry_price, 4),
            "current_price": round(self.current_price, 4),
            "market_value": self.market_value,
            "unrealized_pnl": self.unrealized_pnl,
        }


class Portfolio:
    """
    Thread-safe Portfolio tracker guarded by threading.Lock.
    Tracks cash, open positions, realized and unrealized P&L, and equity.
    """

    def __init__(self, initial_cash: float = 100000.0, session_factory=None):
        self._lock = threading.Lock()
        self.cash_balance: float = float(initial_cash)
        self.realized_pnl: float = 0.0
        self.positions: Dict[str, Position] = {}
        self.session_factory = session_factory or SessionLocal

    def update_market_price(self, symbol: str, price: float):
        with self._lock:
            if symbol in self.positions:
                self.positions[symbol].current_price = float(price)

    def get_position(self, symbol: str) -> Optional[Position]:
        with self._lock:
            pos = self.positions.get(symbol)
            if pos:
                return Position(
                    symbol=pos.symbol,
                    quantity=pos.quantity,
                    avg_entry_price=pos.avg_entry_price,
                    current_price=pos.current_price,
                )
            return None

    def apply_fill(
        self,
        symbol: str,
        side: str,
        qty: float,
        price: float,
        commission: float = 0.0,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Executes a filled trade, adjusting cash, position, and P&L.
        Guaranteed thread-safe via internal Lock.
        """
        side = side.upper()
        fill_price = float(price)
        qty = float(qty)
        commission = float(commission)

        with self._lock:
            if side == "BUY":
                total_cost = (qty * fill_price) + commission
                if total_cost > self.cash_balance:
                    return {
                        "status": "REJECTED",
                        "reason": f"Insufficient cash: required ${total_cost:.2f}, available ${self.cash_balance:.2f}",
                    }

                self.cash_balance -= total_cost

                if symbol not in self.positions:
                    self.positions[symbol] = Position(
                        symbol=symbol,
                        quantity=qty,
                        avg_entry_price=fill_price,
                        current_price=fill_price,
                    )
                else:
                    pos = self.positions[symbol]
                    old_cost = pos.quantity * pos.avg_entry_price
                    new_cost = qty * fill_price
                    total_shares = pos.quantity + qty
                    pos.avg_entry_price = (old_cost + new_cost) / total_shares
                    pos.quantity = total_shares
                    pos.current_price = fill_price

                res = {
                    "status": "FILLED",
                    "symbol": symbol,
                    "side": side,
                    "quantity": qty,
                    "price": fill_price,
                    "commission": commission,
                    "cash_balance": round(self.cash_balance, 2),
                }

            elif side == "SELL":
                pos = self.positions.get(symbol)
                if not pos or pos.quantity <= 0:
                    return {
                        "status": "REJECTED",
                        "reason": f"Cannot SELL {symbol}: no long position held",
                    }

                sell_qty = min(qty, pos.quantity)
                gross_proceeds = sell_qty * fill_price
                net_proceeds = gross_proceeds - commission
                trade_pnl = ((fill_price - pos.avg_entry_price) * sell_qty) - commission

                self.realized_pnl += trade_pnl
                self.cash_balance += net_proceeds
                pos.quantity -= sell_qty
                pos.current_price = fill_price

                if pos.quantity <= 1e-7:
                    pos.quantity = 0.0
                    pos.avg_entry_price = 0.0

                res = {
                    "status": "FILLED",
                    "symbol": symbol,
                    "side": side,
                    "quantity": sell_qty,
                    "price": fill_price,
                    "commission": commission,
                    "trade_pnl": round(trade_pnl, 2),
                    "cash_balance": round(self.cash_balance, 2),
                }
            else:
                return {"status": "REJECTED", "reason": f"Unknown side {side}"}

        if persist:
            self._persist_state(symbol)

        return res

    def get_unrealized_pnl(self) -> float:
        with self._lock:
            return round(
                sum(pos.unrealized_pnl for pos in self.positions.values()), 4
            )

    def get_total_equity(self) -> float:
        with self._lock:
            positions_value = sum(
                pos.market_value for pos in self.positions.values()
            )
            return round(self.cash_balance + positions_value, 4)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            positions_data = {
                s: p.to_dict() for s, p in self.positions.items() if p.quantity > 0
            }
            positions_value = sum(p["market_value"] for p in positions_data.values())
            unrealized = sum(p["unrealized_pnl"] for p in positions_data.values())
            equity = self.cash_balance + positions_value

            return {
                "cash_balance": round(self.cash_balance, 2),
                "total_equity": round(equity, 2),
                "realized_pnl": round(self.realized_pnl, 2),
                "unrealized_pnl": round(unrealized, 2),
                "positions": positions_data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def _persist_state(self, symbol: Optional[str] = None):
        """Persists updated position and snapshot to database."""
        try:
            with db_session(self.session_factory) as session:
                if symbol:
                    with self._lock:
                        pos = self.positions.get(symbol)
                        qty = pos.quantity if pos else 0.0
                        avg_price = pos.avg_entry_price if pos else 0.0

                    db_pos = (
                        session.query(PositionModel)
                        .filter(PositionModel.symbol == symbol)
                        .first()
                    )
                    if db_pos:
                        db_pos.quantity = qty
                        db_pos.avg_entry_price = avg_price
                        db_pos.updated_at = datetime.now(timezone.utc)
                    else:
                        session.add(
                            PositionModel(
                                symbol=symbol,
                                quantity=qty,
                                avg_entry_price=avg_price,
                            )
                        )

                # Persist snapshot
                snap = self.get_snapshot()
                session.add(
                    PortfolioSnapshotModel(
                        cash_balance=snap["cash_balance"],
                        total_equity=snap["total_equity"],
                        realized_pnl=snap["realized_pnl"],
                        unrealized_pnl=snap["unrealized_pnl"],
                        timestamp=datetime.now(timezone.utc),
                    )
                )
        except Exception as e:
            logger.error("Failed to persist portfolio state: %s", e)
