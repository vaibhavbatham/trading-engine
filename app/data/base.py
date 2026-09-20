import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any, Tuple
from queue import Queue, Full

logger = logging.getLogger(__name__)


@dataclass
class Tick:
    """
    Normalized internal market data tick representation.
    Decouples raw external provider formats from downstream strategy and execution engines.
    """
    symbol: str
    price: Decimal
    volume: Optional[Decimal] = None
    timestamp: Optional[datetime] = None
    source: str = "simulation"  # "twelve_data" | "simulation" | "historical_replay"

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)
        elif isinstance(self.timestamp, datetime) and self.timestamp.tzinfo is None:
            self.timestamp = self.timestamp.replace(tzinfo=timezone.utc)

        if not isinstance(self.price, Decimal) and self.price is not None:
            try:
                self.price = Decimal(str(self.price))
            except Exception:
                pass

        if self.volume is not None and not isinstance(self.volume, Decimal):
            try:
                self.volume = Decimal(str(self.volume))
            except Exception:
                pass

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "price": float(self.price) if self.price is not None else None,
            "volume": float(self.volume) if self.volume is not None else None,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "source": self.source,
        }


def validate_tick(tick: Any) -> Tuple[bool, Optional[str]]:
    """
    Validates a normalized Tick before placing it on the queue.
    Ensures:
      - symbol is non-empty string
      - price > 0
      - timestamp is valid and timezone-aware
      - volume is non-negative when provided
      - source is valid
    """
    if not isinstance(tick, Tick):
        return False, f"Expected Tick instance, got {type(tick).__name__}"

    if not tick.symbol or not isinstance(tick.symbol, str) or not tick.symbol.strip():
        return False, "Tick symbol must be a non-empty string"

    if tick.price is None:
        return False, "Tick price is required"

    try:
        price_dec = Decimal(str(tick.price))
        if price_dec <= Decimal("0"):
            return False, f"Tick price must be positive, got {price_dec}"
    except (InvalidOperation, TypeError, ValueError):
        return False, f"Invalid price format: {tick.price}"

    if not isinstance(tick.timestamp, datetime):
        return False, f"Expected datetime timestamp, got {type(tick.timestamp).__name__}"

    if tick.timestamp.tzinfo is None:
        tick.timestamp = tick.timestamp.replace(tzinfo=timezone.utc)

    if tick.volume is not None:
        try:
            vol_dec = Decimal(str(tick.volume))
            if vol_dec < Decimal("0"):
                return False, f"Tick volume cannot be negative, got {vol_dec}"
        except (InvalidOperation, TypeError, ValueError):
            return False, f"Invalid volume format: {tick.volume}"

    if not tick.source or not isinstance(tick.source, str):
        return False, "Tick source must be specified"

    return True, None


class MarketDataProvider(ABC):
    """
    Abstract Base Class for market data sources following Open/Closed Principle.
    """

    def __init__(
        self,
        tick_queue: Queue,
        symbols: Optional[List[str]] = None,
        max_queue_size: int = 10000,
    ):
        self.tick_queue = tick_queue
        self.symbols = [s.upper() for s in (symbols or [])]
        self.max_queue_size = max_queue_size

        # Telemetry metrics
        self.ticks_received: int = 0
        self.ticks_processed: int = 0
        self.dropped_ticks: int = 0
        self.last_tick_time: Optional[datetime] = None
        self.connection_status: str = "disconnected"  # "connected", "reconnecting", "disconnected", "error"
        self.last_error: Optional[str] = None
        self.on_tick_callback: Optional[Callable[[Tick], None]] = None

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the data provider (e.g. 'twelve_data', 'simulator', 'historical_replay')."""
        pass

    @property
    @abstractmethod
    def mode_name(self) -> str:
        """Market data mode ('live', 'simulation', 'replay')."""
        pass

    @abstractmethod
    def start(self):
        """Start the market data provider thread/service."""
        pass

    @abstractmethod
    def stop(self, timeout: float = 3.0):
        """Stop the market data provider gracefully."""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """Check if provider is running."""
        pass

    @abstractmethod
    def subscribe(self, symbols: List[str]):
        """Subscribe to new or updated symbols."""
        pass

    def push_tick(self, tick: Tick) -> bool:
        """
        Validates and pushes a tick onto the queue with queue protection.
        If queue is full, rejects the tick to prevent memory exhaustion and logs metric.
        """
        self.ticks_received += 1

        is_valid, err = validate_tick(tick)
        if not is_valid:
            logger.warning("Rejected invalid market data tick: %s", err)
            return False

        try:
            # Non-blocking put with bounded queue protection
            self.tick_queue.put_nowait(tick)
            self.ticks_processed += 1
            self.last_tick_time = tick.timestamp

            if self.on_tick_callback:
                try:
                    self.on_tick_callback(tick)
                except Exception as cb_err:
                    logger.debug("Error in on_tick_callback: %s", cb_err)

            return True
        except Full:
            self.dropped_ticks += 1
            logger.warning(
                "Queue overflow: queue size %d >= max %d. Dropped tick for %s. Total dropped: %d",
                self.tick_queue.qsize(),
                self.max_queue_size,
                tick.symbol,
                self.dropped_ticks,
            )
            return False

    def get_status(self) -> Dict[str, Any]:
        """Returns standard telemetry dictionary for status API."""
        return {
            "mode": self.mode_name,
            "provider": self.provider_name,
            "connection_status": self.connection_status,
            "symbols": len(self.symbols),
            "symbols_list": list(self.symbols),
            "queue_size": self.tick_queue.qsize(),
            "max_queue_size": self.max_queue_size,
            "ticks_received": self.ticks_received,
            "ticks_processed": self.ticks_processed,
            "dropped_ticks": self.dropped_ticks,
            "last_tick": self.last_tick_time.isoformat() if self.last_tick_time else None,
            "last_error": self.last_error,
        }
