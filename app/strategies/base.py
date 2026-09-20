from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Deque

from app.data_feed import Tick


@dataclass
class Signal:
    symbol: str
    strategy_name: str
    signal_type: str  # "BUY", "SELL", "HOLD"
    price: float
    timestamp: datetime

    def to_dict(self):
        return {
            "symbol": self.symbol,
            "strategy_name": self.strategy_name,
            "signal_type": self.signal_type,
            "price": round(float(self.price), 4),
            "timestamp": self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else str(self.timestamp),
        }


class Strategy(ABC):
    """
    Abstract Base Class for trading strategies following the Strategy Pattern.
    """

    def __init__(self, symbol: str, params: Optional[Dict[str, Any]] = None, maxlen: int = 100):
        self.symbol = symbol
        self.params: Dict[str, Any] = params or {}
        self.prices: Deque[float] = deque(maxlen=maxlen)
        self.last_signal_type: Optional[str] = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy human-readable identifier."""
        pass

    @abstractmethod
    def update(self, tick: Tick) -> Optional[Signal]:
        """
        Process a new incoming tick and evaluate strategy conditions.
        Returns a Signal if an actionable trade triggers, else None.
        """
        pass

    def reset(self):
        """Reset internal indicator state."""
        self.prices.clear()
        self.last_signal_type = None
