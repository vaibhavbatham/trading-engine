import random
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict
from queue import Queue

from app.data.base import MarketDataProvider, Tick
from app.config import settings

logger = logging.getLogger(__name__)

DEFAULT_SIM_PRICES = {
    "AAPL": 185.50,
    "MSFT": 425.00,
    "GOOGL": 175.25,
    "AMZN": 182.40,
    "TSLA": 215.80,
    "NVDA": 125.40,
    "META": 505.60,
}


class SimulationProvider(MarketDataProvider):
    """
    Simulated real-time market data provider producing synthetic Brownian random-walk ticks.
    Guarantees isolation of testing and development from live data dependencies.
    """

    def __init__(
        self,
        tick_queue: Queue,
        symbols: Optional[List[str]] = None,
        initial_prices: Optional[Dict[str, float]] = None,
        interval: float = 1.0,
        volatility: float = 0.001,
        max_queue_size: int = 10000,
    ):
        super().__init__(tick_queue, symbols or settings.SYMBOLS, max_queue_size)
        self.initial_prices = initial_prices or DEFAULT_SIM_PRICES
        self.prices: Dict[str, float] = {
            s: self.initial_prices.get(s, 150.0) for s in self.symbols
        }
        self.interval = interval
        self.volatility = volatility

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def provider_name(self) -> str:
        return "simulator"

    @property
    def mode_name(self) -> str:
        return "simulation"

    def subscribe(self, symbols: List[str]):
        """Dynamically add or update simulated symbol set."""
        for sym in symbols:
            s_up = sym.upper()
            if s_up not in self.symbols:
                self.symbols.append(s_up)
                self.prices[s_up] = self.initial_prices.get(s_up, 150.0)
        logger.info("SimulationProvider active symbols updated: %s", self.symbols)

    def generate_next_tick(self, symbol: str) -> Tick:
        current_price = self.prices.get(symbol, 100.0)
        shock = random.gauss(0, self.volatility)
        new_price = max(0.01, round(current_price * (1.0 + shock), 4))
        self.prices[symbol] = new_price
        volume = random.randint(50, 500)
        now_utc = datetime.now(timezone.utc)

        return Tick(
            symbol=symbol,
            price=Decimal(str(new_price)),
            volume=Decimal(str(volume)),
            timestamp=now_utc,
            source="simulation",
        )

    def _run_loop(self):
        logger.info("SimulationProvider started for symbols: %s", self.symbols)
        self.connection_status = "connected"

        while not self._stop_event.is_set():
            for symbol in list(self.symbols):
                tick = self.generate_next_tick(symbol)
                self.push_tick(tick)

            self._stop_event.wait(self.interval)

        self.connection_status = "disconnected"
        logger.info("SimulationProvider loop ended.")

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            logger.warning("SimulationProvider is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="SimulationProviderThread",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0):
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping SimulationProvider...")
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self._thread = None
        self.connection_status = "disconnected"
        logger.info("SimulationProvider stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
