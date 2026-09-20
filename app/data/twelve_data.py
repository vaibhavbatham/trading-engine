import json
import logging
import threading
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, List, Dict, Any, Callable
from queue import Queue

try:
    from websockets.sync.client import connect as ws_connect
except ImportError:
    ws_connect = None

from app.data.base import MarketDataProvider, Tick
from app.config import settings

logger = logging.getLogger(__name__)


class TwelveDataProvider(MarketDataProvider):
    """
    Production-grade market data provider streaming real-time quotes from Twelve Data WebSocket API.
    Features:
      - Authentication and symbol subscription
      - Bounded exponential backoff reconnection (1s -> 30s)
      - Incoming message validation and normalization
      - Thread-safe background execution with graceful shutdown
      - Queue overflow protection
    """

    def __init__(
        self,
        tick_queue: Queue,
        api_key: Optional[str] = None,
        symbols: Optional[List[str]] = None,
        max_queue_size: int = 10000,
        ws_url: str = "wss://ws.twelvedata.com/v1/quotes/price",
        connect_fn: Optional[Callable] = None,
        reconnect_backoff_initial: float = 1.0,
        reconnect_backoff_max: float = 30.0,
    ):
        super().__init__(tick_queue, symbols or settings.SYMBOLS, max_queue_size)
        resolved_key = api_key if api_key is not None else settings.TWELVE_DATA_API_KEY
        if not resolved_key or not str(resolved_key).strip():
            raise ValueError("TWELVE_DATA_API_KEY is required for TwelveDataProvider")

        self.api_key = str(resolved_key).strip()
        self.ws_url = ws_url
        self.connect_fn = connect_fn or ws_connect
        self.reconnect_backoff_initial = reconnect_backoff_initial
        self.reconnect_backoff_max = reconnect_backoff_max

        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._current_backoff: float = reconnect_backoff_initial
        self._max_backoff: float = reconnect_backoff_max
        self._ws_client = None

    @property
    def full_url(self) -> str:
        return f"{self.ws_url}?apikey={self.api_key}"

    @property
    def provider_name(self) -> str:
        return "twelve_data"

    @property
    def mode_name(self) -> str:
        return "live"

    def _send_subscription(self, ws):
        """Sends the subscription command over the websocket."""
        sub_msg = {
            "action": "subscribe",
            "params": {
                "symbols": ",".join(self.symbols)
            }
        }
        ws.send(json.dumps(sub_msg))

    def subscribe(self, symbols: List[str]):
        """Update subscribed symbols and send subscription command if connected."""
        self.symbols = [s.upper() for s in symbols]
        if self._ws_client:
            try:
                self._send_subscription(self._ws_client)
                logger.info("Sent Twelve Data subscription update for %s", self.symbols)
            except Exception as e:
                logger.error("Failed sending subscription update: %s", e)

    def parse_message(self, data: Dict[str, Any]) -> Optional[Tick]:
        """
        Validates raw Twelve Data JSON message and normalizes it to our internal Tick model.
        Returns None if message is not a price event or fails validation.
        """
        if not isinstance(data, dict):
            logger.warning("Received non-dict Twelve Data message: %s", data)
            return None

        event = data.get("event")

        # Handle subscription status or error acknowledgements
        if event == "subscribe-status":
            if data.get("status") == "error":
                self.last_error = data.get("message", "Subscription error")
                self.connection_status = "error"
                logger.error("Twelve Data subscription error: %s", self.last_error)
            else:
                logger.info("Twelve Data subscription acknowledged: %s", data.get("success", []))
            return None

        if data.get("status") == "error":
            self.last_error = data.get("message", "Provider error")
            self.connection_status = "error"
            logger.error("Twelve Data error message: %s", self.last_error)
            return None

        if event == "heartbeat":
            logger.debug("Twelve Data heartbeat received.")
            return None

        # Price update event
        if event == "price":
            symbol = data.get("symbol")
            if not symbol or not isinstance(symbol, str):
                logger.warning("Twelve Data price message missing symbol: %s", data)
                return None
            symbol = symbol.upper()

            price_raw = data.get("price")
            if price_raw is None:
                logger.warning("Twelve Data price message missing price field: %s", data)
                return None

            try:
                price_dec = Decimal(str(price_raw))
                if price_dec <= Decimal("0"):
                    logger.warning("Twelve Data price <= 0: %s", price_dec)
                    return None
            except (InvalidOperation, TypeError, ValueError) as err:
                logger.warning("Twelve Data invalid price %s: %s", price_raw, err)
                return None

            vol_raw = data.get("day_volume") if "day_volume" in data else data.get("volume")
            vol_dec = None
            if vol_raw is not None:
                try:
                    vol_dec = Decimal(str(vol_raw))
                    if vol_dec < Decimal("0"):
                        logger.warning("Twelve Data negative volume %s", vol_dec)
                        return None
                except (InvalidOperation, TypeError, ValueError):
                    vol_dec = None

            ts_raw = data.get("timestamp")
            if ts_raw is not None and isinstance(ts_raw, (int, float)):
                try:
                    dt = datetime.fromtimestamp(ts_raw, timezone.utc)
                except Exception:
                    dt = datetime.now(timezone.utc)
            else:
                dt = datetime.now(timezone.utc)

            return Tick(
                symbol=symbol,
                price=price_dec,
                volume=vol_dec,
                timestamp=dt,
                source="twelve_data",
            )

        logger.debug("Ignored unhandled Twelve Data event: %s", event)
        return None

    def _handle_message(self, raw_msg: str):
        """Decodes raw WebSocket frame, parses normalized Tick, and enqueues it."""
        try:
            parsed_json = json.loads(raw_msg)
        except json.JSONDecodeError as jde:
            logger.error("Malformed JSON received from Twelve Data: %s", jde)
            return

        tick = self.parse_message(parsed_json)
        if tick is not None:
            self.push_tick(tick)

    def _run_loop(self):
        logger.info("TwelveDataProvider background worker started.")

        if not self.api_key or not self.api_key.strip():
            err_msg = "TWELVE_DATA_API_KEY is not configured. Cannot connect to Twelve Data WebSocket."
            self.connection_status = "error"
            self.last_error = err_msg
            logger.error(err_msg)
            return

        if self.connect_fn is None:
            err_msg = "WebSocket client library not available."
            self.connection_status = "error"
            self.last_error = err_msg
            logger.error(err_msg)
            return

        target_url = self.full_url

        while not self._stop_event.is_set():
            try:
                self.connection_status = "reconnecting" if self._current_backoff > self.reconnect_backoff_initial else "connecting"
                logger.info("Establishing connection to Twelve Data at %s...", self.ws_url)

                with self.connect_fn(target_url, open_timeout=10, close_timeout=5) as ws:
                    self._ws_client = ws
                    self.connection_status = "connected"
                    self.last_error = None
                    self._current_backoff = self.reconnect_backoff_initial  # Reset backoff upon successful connection
                    logger.info("Connected to Twelve Data WebSocket. Subscribing to: %s", self.symbols)

                    # Send subscribe message
                    self._send_subscription(ws)

                    # Continuous message receive loop
                    while not self._stop_event.is_set():
                        try:
                            # Use timeout so loop periodically checks _stop_event
                            raw_msg = ws.recv(timeout=1.0)
                        except TimeoutError:
                            continue
                        except Exception as read_err:
                            if self._stop_event.is_set():
                                break
                            raise read_err

                        self._handle_message(raw_msg)

            except Exception as e:
                self._ws_client = None
                if self._stop_event.is_set():
                    break

                self.connection_status = "reconnecting"
                self.last_error = str(e)
                logger.warning(
                    "Twelve Data connection failed: %s. Reconnecting with backoff in %.1fs...",
                    e,
                    self._current_backoff,
                )

                # Wait for backoff duration or shutdown event
                self._stop_event.wait(self._current_backoff)
                # Exponential backoff bounded by max 30s
                self._current_backoff = min(self._max_backoff, self._current_backoff * 2.0)

        self._ws_client = None
        self.connection_status = "disconnected"
        logger.info("TwelveDataProvider loop terminated gracefully.")

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            logger.warning("TwelveDataProvider is already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="TwelveDataProviderThread",
            daemon=True,
        )
        self._thread.start()

    def stop(self, timeout: float = 3.0):
        if self._thread is None or not self._thread.is_alive():
            return

        logger.info("Stopping TwelveDataProvider...")
        self._stop_event.set()
        if self._ws_client is not None:
            try:
                self._ws_client.close()
            except Exception:
                pass

        self._thread.join(timeout=timeout)
        self._thread = None
        self.connection_status = "disconnected"
        logger.info("TwelveDataProvider stopped.")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
