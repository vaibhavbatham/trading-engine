import queue
import logging
import threading
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable

from app.data_feed import Tick
from app.strategies.base import Strategy, Signal
from app.strategies.moving_average import MovingAverageCrossover
from app.strategies.rsi import RSIStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.engine.order_executor import OrderExecutor
from app.models import SignalModel
from app.db import db_session, SessionLocal

logger = logging.getLogger(__name__)


class SignalEngine:
    """
    Consumer thread that reads Ticks from the shared queue, updates
    all active strategies for each symbol, commits generated signals
    to the database, and dispatches them to the OrderExecutor.
    """

    def __init__(
        self,
        tick_queue: queue.Queue,
        order_executor: Optional[OrderExecutor] = None,
        symbols: Optional[List[str]] = None,
        session_factory=None,
        on_signal_callback: Optional[Callable[[Signal], None]] = None,
        strategy_factories: Optional[List[Callable[[str], Strategy]]] = None,
    ):
        self.tick_queue = tick_queue
        self.order_executor = order_executor
        self.symbols = symbols or ["AAPL", "GOOGL", "MSFT", "TSLA", "AMZN"]
        self.session_factory = session_factory or SessionLocal
        self.on_signal_callback = on_signal_callback

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

        # Build active strategy instances per symbol
        default_factories = [
            lambda sym: MovingAverageCrossover(sym, {"fast_period": 5, "slow_period": 20}),
            lambda sym: RSIStrategy(sym, {"period": 14, "oversold": 30.0, "overbought": 70.0}),
            lambda sym: MeanReversionStrategy(sym, {"period": 20, "num_std": 2.0}),
        ]
        factories = strategy_factories if strategy_factories is not None else default_factories

        self.strategies: Dict[str, List[Strategy]] = {
            sym: [f(sym) for f in factories] for sym in self.symbols
        }

    def process_tick(self, tick: Tick) -> List[Signal]:
        """Synchronously process a single tick through relevant strategies."""
        # Update current market price in portfolio
        if self.order_executor and self.order_executor.portfolio:
            self.order_executor.portfolio.update_market_price(tick.symbol, float(tick.price))

        emitted_signals: List[Signal] = []
        symbol_strategies = self.strategies.get(tick.symbol, [])

        for strat in symbol_strategies:
            sig = strat.update(tick)
            if sig:
                logger.info("Signal generated: %s %s @ $%.2f from %s", sig.signal_type, sig.symbol, sig.price, sig.strategy_name)
                self._record_signal(sig)
                if self.order_executor:
                    self.order_executor.execute_signal(sig)
                if self.on_signal_callback:
                    try:
                        self.on_signal_callback(sig)
                    except Exception as cb_err:
                        logger.error("Error in signal callback: %s", cb_err)
                emitted_signals.append(sig)

        return emitted_signals

    def _record_signal(self, sig: Signal):
        try:
            with db_session(self.session_factory) as session:
                model = SignalModel(
                    symbol=sig.symbol,
                    strategy_name=sig.strategy_name,
                    signal_type=sig.signal_type,
                    price=sig.price,
                    timestamp=sig.timestamp,
                )
                session.add(model)
        except Exception as e:
            logger.error("Failed to record signal: %s", e)

    def _run_loop(self):
        logger.info("SignalEngine consumer started.")
        while not self._stop_event.is_set():
            try:
                tick: Tick = self.tick_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                self.process_tick(tick)
            except Exception as e:
                logger.error("Error processing tick in SignalEngine: %s", e)
            finally:
                self.tick_queue.task_done()

        logger.info("SignalEngine loop exited.")

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            logger.warning("SignalEngine is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="SignalEngineThread", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 3.0):
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping SignalEngine...")
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self._thread = None
        logger.info("SignalEngine stopped.")

    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
