from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    Numeric,
    DateTime,
    Index,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def utc_now():
    return datetime.now(timezone.utc)


class TickModel(Base):
    __tablename__ = "ticks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(16), nullable=False, index=True)
    price = Column(Numeric(14, 4), nullable=False)
    volume = Column(Numeric(18, 4), nullable=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    source = Column(String(32), nullable=False, default="simulation", index=True)

    __table_args__ = (
        Index("ix_ticks_symbol_timestamp", "symbol", "timestamp"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "price": float(self.price),
            "volume": float(self.volume) if self.volume is not None else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
        }


class SignalModel(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(16), nullable=False, index=True)
    strategy_name = Column(String(64), nullable=False)
    signal_type = Column(String(16), nullable=False)  # BUY, SELL, HOLD
    price = Column(Numeric(14, 4), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "signal_type": self.signal_type,
            "price": float(self.price),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class OrderModel(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(16), nullable=False, index=True)
    side = Column(String(8), nullable=False)  # BUY, SELL
    quantity = Column(Float, nullable=False)
    price = Column(Numeric(14, 4), nullable=False)
    status = Column(String(16), nullable=False, default="FILLED")  # FILLED, REJECTED
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side,
            "quantity": float(self.quantity),
            "price": float(self.price),
            "status": self.status,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class PositionModel(Base):
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(16), nullable=False, unique=True, index=True)
    quantity = Column(Float, nullable=False, default=0.0)
    avg_entry_price = Column(Numeric(14, 4), nullable=False, default=0.0)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)

    def to_dict(self):
        return {
            "id": self.id,
            "symbol": self.symbol,
            "quantity": float(self.quantity),
            "avg_entry_price": float(self.avg_entry_price),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class PortfolioSnapshotModel(Base):
    __tablename__ = "portfolio_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    cash_balance = Column(Numeric(14, 4), nullable=False)
    total_equity = Column(Numeric(14, 4), nullable=False)
    realized_pnl = Column(Numeric(14, 4), nullable=False, default=0.0)
    unrealized_pnl = Column(Numeric(14, 4), nullable=False, default=0.0)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=utc_now, index=True)

    def to_dict(self):
        return {
            "id": self.id,
            "cash_balance": float(self.cash_balance),
            "total_equity": float(self.total_equity),
            "realized_pnl": float(self.realized_pnl),
            "unrealized_pnl": float(self.unrealized_pnl),
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }
