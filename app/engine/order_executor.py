import logging
import math
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from app.strategies.base import Signal
from app.engine.portfolio import Portfolio
from app.models import OrderModel
from app.db import db_session, SessionLocal

logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    Handles trade generation, sizing, risk management, slippage modeling,
    and fill simulation.
    """

    def __init__(
        self,
        portfolio: Portfolio,
        position_size_pct: float = 0.10,
        fixed_shares: Optional[float] = None,
        slippage_pct: float = 0.0005,
        commission: float = 1.00,
        max_position_equity_pct: float = 0.25,
        session_factory=None,
    ):
        self.portfolio = portfolio
        self.position_size_pct = position_size_pct
        self.fixed_shares = fixed_shares
        self.slippage_pct = slippage_pct
        self.commission = commission
        self.max_position_equity_pct = max_position_equity_pct
        self.session_factory = session_factory or SessionLocal

    def execute_signal(self, signal: Signal) -> Dict[str, Any]:
        """
        Processes an incoming trading signal, applies risk controls and sizing,
        simulates the fill with slippage/commission, and commits order to DB.
        """
        side = signal.signal_type.upper()
        symbol = signal.symbol
        price = float(signal.price)

        if side not in ("BUY", "SELL"):
            return {"status": "IGNORED", "reason": f"Signal type {side} not executable"}

        if side == "BUY":
            # Position sizing
            if self.fixed_shares:
                qty = float(self.fixed_shares)
            else:
                target_spend = self.portfolio.cash_balance * self.position_size_pct
                if target_spend < price:
                    qty = 1.0
                else:
                    qty = max(1.0, math.floor(target_spend / price))

            # Simulate execution price with slippage
            fill_price = round(price * (1.0 + self.slippage_pct), 4)

            # Enforce Risk Limit: Maximum position size as % of total equity
            total_equity = self.portfolio.get_total_equity()
            current_pos = self.portfolio.get_position(symbol)
            current_shares = current_pos.quantity if current_pos else 0.0
            new_position_value = (current_shares + qty) * fill_price

            if total_equity > 0 and (new_position_value / total_equity) > self.max_position_equity_pct:
                logger.warning(
                    "BUY %s rejected: Proposed position $%.2f exceeds %.1f%% of equity $%.2f",
                    symbol,
                    new_position_value,
                    self.max_position_equity_pct * 100,
                    total_equity,
                )
                self._record_order(symbol, side, qty, fill_price, "REJECTED")
                return {
                    "status": "REJECTED",
                    "reason": f"Risk limit exceeded: {new_position_value / total_equity:.1%} > {self.max_position_equity_pct:.1%}",
                }

            # Attempt fill in portfolio
            fill_res = self.portfolio.apply_fill(
                symbol=symbol,
                side=side,
                qty=qty,
                price=fill_price,
                commission=self.commission,
            )

            status = fill_res.get("status", "REJECTED")
            self._record_order(symbol, side, qty, fill_price, status)
            return fill_res

        elif side == "SELL":
            current_pos = self.portfolio.get_position(symbol)
            if not current_pos or current_pos.quantity <= 0:
                logger.info("SELL %s skipped: No position held.", symbol)
                self._record_order(symbol, side, 0.0, price, "REJECTED")
                return {
                    "status": "REJECTED",
                    "reason": f"No long position held for {symbol}",
                }

            qty = current_pos.quantity
            fill_price = round(price * (1.0 - self.slippage_pct), 4)

            fill_res = self.portfolio.apply_fill(
                symbol=symbol,
                side=side,
                qty=qty,
                price=fill_price,
                commission=self.commission,
            )

            status = fill_res.get("status", "REJECTED")
            self._record_order(symbol, side, qty, fill_price, status)
            return fill_res

        return {"status": "UNKNOWN"}

    def _record_order(self, symbol: str, side: str, qty: float, price: float, status: str):
        try:
            with db_session(self.session_factory) as session:
                order = OrderModel(
                    symbol=symbol,
                    side=side,
                    quantity=qty,
                    price=price,
                    status=status,
                    timestamp=datetime.now(timezone.utc),
                )
                session.add(order)
        except Exception as e:
            logger.error("Failed to record order to DB: %s", e)
