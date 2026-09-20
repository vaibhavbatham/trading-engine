import time
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from queue import Queue

from app.data.base import MarketDataProvider, Tick
from app.models import TickModel
from app.db import db_session, SessionLocal
from app.config import settings

logger = logging.getLogger(__name__)


class HistoricalReplayProvider(MarketDataProvider):
    """
    Historical market data provider that replays recorded tick data chronologically
    from PostgreSQL or a preloaded dataset through the exact same queue used by live data.
    """

    def __init__(
        self,
        tick_queue: Queue,
        symbols: Optional[List[str]] = None,
        replay_speed: float = 1.0,
        ticks_dataset: Optional[List[Tick]] = None,
        session_factory=None,
        max_queue_size: int = 10000,
    ):
        super().__init__(tick_queue, symbols or settings.SYMBOLS, max_queue_size)
        self.replay_speed = replay_speed
        self.ticks_dataset = ticks_dataset
        self.session_factory = session_factory or SessionLocal

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @property
    def provider_name(self) -> str:
        return "historical_replay"

    @property
    def mode_name(self) -> str:
        return "replay"

    def subscribe(self, symbols: List[str]):
        self.symbols = [s.upper() for s in symbols]

    def _fetch_db_ticks(self) -> List[Tick]:
        """Fetch chronological tick history from database."""
        ticks: List[Tick] = []
        try:
            with db_session(self.session_factory) as session:
                query = session.query(TickModel)
                if self.symbols:
                    query = query.filter(TickModel.symbol.in_(self.symbols))
                records = query.order_by(TickModel.timestamp.asc()).limit(5000).all()

                for r in records:
                    ts = r.timestamp if r.timestamp.tzinfo else r.timestamp.replace(tzinfo=timezone.utc)
                    ticks.append(
                        Tick(
                            symbol=r.symbol,
                            price=Decimal(str(r.price)),
                            volume=Decimal(str(r.volume)) if r.volume is not None else None,
                            timestamp=ts,
                            source="historical_replay",
                        )
                    )
        except Exception as e:
            logger.error("Failed to load historical ticks from database: %s", e)
            self.last_error = str(e)
        return ticks

    def _run_loop(self):
        logger.info("HistoricalReplayProvider starting replay...")
        self.connection_status = "connected"

        # Obtain ticks from provided dataset or query database
        data_source = self.ticks_dataset if self.ticks_dataset is not None else self._fetch_db_ticks()

        if not data_source:
            logger.warning("No historical ticks available for replay.")
            self.connection_status = "disconnected"
            return

        logger.info("Replaying %d historical ticks...", len(data_source))

        prev_timestamp: Optional[datetime] = None

        for tick in data_source:
            if self._stop_event.is_set():
                break

            # Calculate inter-tick delay based on timestamps and replay speed
            if prev_timestamp and self.replay_speed > 0:
                delta_sec = (tick.timestamp - prev_timestamp).total_seconds()
                delay = max(0.0, min(delta_sec / self.replay_speed, 2.0))
                if delay > 0.001:
                    self._stop_event.wait(delay)

            prev_timestamp = tick.timestamp

            # Ensure tick source tag is normalized
            replay_tick = Tick(
                symbol=tick.symbol,
                price=tick.price,
                volume=tick.volume,
                timestamp=tick.timestamp,
                source="historical_replay",
            )
            self.push_tick(replay_tick)

        self.connection_status = "disconnected"
        logger.info("HistoricalReplayProvider finished replaying data.")

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            logger.warning("HistoricalReplayProvider is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="HistoricalReplayThread",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0):
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping HistoricalReplayProvider...")
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self._thread = None
        self.connection_status = "disconnected"
        logger.info("HistoricalReplayProvider stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
