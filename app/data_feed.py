import time
import logging
import threading
from typing import Dict, List, Optional, Any
from queue import Queue, Empty

from app.data.base import Tick, MarketDataProvider
from app.data.twelve_data import TwelveDataProvider
from app.data.simulator import SimulationProvider
from app.data.replay import HistoricalReplayProvider
from app.models import TickModel
from app.db import db_session, SessionLocal
from app.config import settings

logger = logging.getLogger(__name__)


class MarketDataFeed:
    """
    Core Producer component in the trading engine's producer-consumer architecture.
    Orchestrates the active MarketDataProvider (Twelve Data, Simulator, or Replay),
    routes validated Ticks into the shared Queue for SignalEngine,
    and batches database persistence asynchronously without blocking the feed.
    """

    def __init__(
        self,
        tick_queue: Queue,
        mode: Optional[str] = None,
        provider: Optional[MarketDataProvider] = None,
        symbols: Optional[List[str]] = None,
        batch_size: int = 10,
        session_factory=None,
        persist_to_db: bool = True,
        max_queue_size: int = 10000,
        **provider_kwargs,
    ):
        self.tick_queue = tick_queue
        self.mode = (mode or settings.MARKET_DATA_MODE).lower()
        self.symbols = symbols or settings.SYMBOLS
        self.batch_size = batch_size
        self.session_factory = session_factory or SessionLocal
        self.persist_to_db = persist_to_db
        self.max_queue_size = max_queue_size

        # Provider initialization
        if provider is not None:
            self.provider = provider
        else:
            self.provider = self._create_provider(**provider_kwargs)

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._buffer: List[Tick] = []
        self._buffer_lock = threading.Lock()
        self.latest_ticks: Dict[str, Tick] = {}

        # Wire callback to receive ticks from provider in real-time
        self.provider.on_tick_callback = self._on_tick

    def _on_tick(self, tick: Tick):
        """Called whenever provider validates and pushes a new tick."""
        self.latest_ticks[tick.symbol] = tick
        if self.persist_to_db:
            with self._buffer_lock:
                self._buffer.append(tick)
                if len(self._buffer) >= self.batch_size:
                    # Flush in background / direct
                    pass

    def get_latest_ticks(self) -> Dict[str, Dict[str, Any]]:
        """Returns the most recent ticks per symbol for instant UI streaming."""
        return {sym: t.to_dict() for sym, t in self.latest_ticks.items()}

    def _create_provider(self, **kwargs) -> MarketDataProvider:
        """Factory method to instantiate the configured market data provider."""
        if self.mode == "live":
            logger.info("Initializing Live TwelveDataProvider...")
            td_keys = {"ws_url", "connect_fn", "reconnect_backoff_initial", "reconnect_backoff_max"}
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in td_keys}
            return TwelveDataProvider(
                tick_queue=self.tick_queue,
                api_key=settings.TWELVE_DATA_API_KEY,
                symbols=self.symbols,
                max_queue_size=self.max_queue_size,
                **filtered_kwargs,
            )
        elif self.mode == "replay":
            logger.info("Initializing HistoricalReplayProvider...")
            return HistoricalReplayProvider(
                tick_queue=self.tick_queue,
                symbols=self.symbols,
                session_factory=self.session_factory,
                max_queue_size=self.max_queue_size,
                **kwargs,
            )
        else:
            logger.info("Initializing SimulationProvider (Brownian random-walk)...")
            sim_kwargs = {
                "interval": settings.TICK_INTERVAL_SECONDS,
                "volatility": settings.TICK_VOLATILITY,
                "max_queue_size": self.max_queue_size,
            }
            sim_kwargs.update(kwargs)
            return SimulationProvider(
                tick_queue=self.tick_queue,
                symbols=self.symbols,
                **sim_kwargs,
            )

    def _flush_buffer(self):
        with self._buffer_lock:
            if not self._buffer or not self.persist_to_db:
                self._buffer.clear()
                return

            ticks_to_save = list(self._buffer)
            self._buffer.clear()

        try:
            with db_session(self.session_factory) as session:
                models = [
                    TickModel(
                        symbol=t.symbol,
                        price=float(t.price),
                        volume=float(t.volume) if t.volume is not None else None,
                        timestamp=t.timestamp,
                        source=t.source,
                    )
                    for t in ticks_to_save
                ]
                session.add_all(models)
                logger.debug("Batched %d ticks into database.", len(models))
        except Exception as e:
            logger.error("Failed to batch persist ticks: %s", e)

    def _batch_listener_loop(self):
        """
        Background persistence loop that flushes tick batches periodically.
        """
        while not self._stop_event.is_set():
            self._stop_event.wait(2.0)
            self._flush_buffer()

        self._flush_buffer()

    def start(self):
        """Starts the underlying market data provider and the persistence listener."""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("MarketDataFeed is already running.")
            return

        self._stop_event.clear()
        self.provider.start()

        self._thread = threading.Thread(
            target=self._batch_listener_loop,
            name="MarketDataFeedBatchThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("MarketDataFeed producer started in '%s' mode.", self.mode)

    def stop(self, timeout: float = 3.0):
        """Stops the market data provider and flushes any remaining buffered ticks."""
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping MarketDataFeed...")
        self._stop_event.set()
        self.provider.stop(timeout=timeout)
        self._thread.join(timeout=timeout)
        self._thread = None
        self._flush_buffer()
        logger.info("MarketDataFeed stopped.")

    def is_alive(self) -> bool:
        return self.provider.is_running()

    def generate_next_tick(self, symbol: str) -> Tick:
        """Delegates synthetic tick generation to provider if supported."""
        if hasattr(self.provider, "generate_next_tick"):
            return self.provider.generate_next_tick(symbol)
        raise NotImplementedError(
            f"Provider {self.provider.__class__.__name__} does not support generate_next_tick"
        )

    def get_status(self) -> Dict[str, Any]:
        """Provides consolidated market data status."""
        status = self.provider.get_status()
        status["feed_alive"] = self.is_alive()
        status["mode"] = self.mode
        return status

    def switch_provider(
        self,
        new_mode: str,
        api_key: Optional[str] = None,
        symbols: Optional[List[str]] = None,
    ):
        """
        Dynamically hot-swaps the active market data provider at runtime.
        Safely stops the previous provider thread, updates settings, and starts the new provider.
        """
        mode_clean = new_mode.lower().strip()
        if mode_clean not in ("live", "simulation", "replay"):
            raise ValueError(f"Invalid mode '{new_mode}'. Supported modes: 'live', 'simulation', 'replay'")

        if mode_clean == "live":
            if api_key is not None and not str(api_key).strip():
                raise ValueError("TWELVE_DATA_API_KEY is required to switch to 'live' mode.")
            target_key = api_key.strip() if api_key else settings.TWELVE_DATA_API_KEY
            if not target_key or not str(target_key).strip():
                raise ValueError("TWELVE_DATA_API_KEY is required to switch to 'live' mode.")
            settings.TWELVE_DATA_API_KEY = str(target_key).strip()

        if symbols:
            clean_syms = [s.strip().upper() for s in symbols if s.strip()]
            if clean_syms:
                self.symbols = clean_syms
                settings.SYMBOLS = clean_syms

        # Stop current provider
        was_running = self.is_alive()
        logger.info("Stopping current provider '%s' to switch to '%s' mode...", self.provider.provider_name, mode_clean)
        self.provider.stop(timeout=2.0)

        # Update mode
        self.mode = mode_clean
        settings.MARKET_DATA_MODE = mode_clean

        # Instantiate new provider
        self.provider = self._create_provider()
        self.provider.on_tick_callback = self._on_tick

        # Restart new provider if the feed thread is running or was running
        if was_running or (self._thread is not None and self._thread.is_alive()):
            self.provider.start()

        logger.info("MarketDataFeed provider switched successfully to '%s' in '%s' mode.", self.provider.provider_name, self.mode)
        return True, f"Market data provider successfully switched to {self.provider.provider_name} ({self.mode} mode)."

