import json
import time
from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from app.data.twelve_data import TwelveDataProvider


def test_twelve_data_missing_api_key_raises():
    q = Queue()
    with pytest.raises(ValueError, match="TWELVE_DATA_API_KEY is required"):
        TwelveDataProvider(tick_queue=q, api_key="", symbols=["AAPL"])

    with pytest.raises(ValueError, match="TWELVE_DATA_API_KEY is required"):
        TwelveDataProvider(tick_queue=q, api_key=None, symbols=["AAPL"])


def test_twelve_data_connect_url_and_subscription_payload():
    q = Queue()
    provider = TwelveDataProvider(
        tick_queue=q,
        api_key="test_secret_key",
        symbols=["AAPL", "MSFT"],
    )

    assert provider.full_url == "wss://ws.twelvedata.com/v1/quotes/price?apikey=test_secret_key"

    mock_ws = MagicMock()
    provider._send_subscription(mock_ws)

    mock_ws.send.assert_called_once()
    sent_payload = json.loads(mock_ws.send.call_args[0][0])
    assert sent_payload["action"] == "subscribe"
    assert "AAPL,MSFT" in sent_payload["params"]["symbols"]


def test_twelve_data_price_event_parsing():
    q = Queue()
    provider = TwelveDataProvider(
        tick_queue=q,
        api_key="test_key",
        symbols=["AAPL"],
    )

    raw_event = json.dumps({
        "event": "price",
        "symbol": "AAPL",
        "price": 185.75,
        "day_volume": 45000000,
        "timestamp": 1710000000,
    })

    provider._handle_message(raw_event)

    assert not q.empty()
    tick = q.get_nowait()
    assert tick.symbol == "AAPL"
    assert tick.price == Decimal("185.75")
    assert tick.volume == Decimal("45000000")
    assert tick.source == "twelve_data"
    assert tick.timestamp is not None
    assert provider.ticks_processed == 1


def test_twelve_data_heartbeat_and_subscribe_status():
    q = Queue()
    provider = TwelveDataProvider(
        tick_queue=q,
        api_key="test_key",
        symbols=["AAPL"],
    )

    # Heartbeat
    provider._handle_message(json.dumps({"event": "heartbeat", "status": "ok"}))
    assert q.empty()

    # Subscribe-status
    provider._handle_message(json.dumps({
        "event": "subscribe-status",
        "status": "ok",
        "success": [{"symbol": "AAPL", "type": "price"}],
        "fails": None,
    }))
    assert q.empty()
    assert provider.last_error is None


def test_twelve_data_error_event_handling():
    q = Queue()
    provider = TwelveDataProvider(
        tick_queue=q,
        api_key="test_key",
        symbols=["AAPL"],
    )

    provider._handle_message(json.dumps({
        "status": "error",
        "message": "API key limit exceeded",
    }))

    assert q.empty()
    assert "API key limit exceeded" in provider.last_error
    assert provider.connection_status == "error"


def test_twelve_data_malformed_json_handling():
    q = Queue()
    provider = TwelveDataProvider(
        tick_queue=q,
        api_key="test_key",
        symbols=["AAPL"],
    )

    # Malformed non-JSON
    provider._handle_message("NOT_VALID_JSON{:::}")
    assert q.empty()
    assert provider.ticks_processed == 0


def test_twelve_data_backoff_calculation():
    q = Queue()
    provider = TwelveDataProvider(
        tick_queue=q,
        api_key="test_key",
        symbols=["AAPL"],
        reconnect_backoff_initial=1.0,
        reconnect_backoff_max=30.0,
    )

    backoff = provider.reconnect_backoff_initial
    assert backoff == 1.0
    backoff = min(backoff * 2.0, provider.reconnect_backoff_max)
    assert backoff == 2.0
    backoff = min(backoff * 2.0, provider.reconnect_backoff_max)
    assert backoff == 4.0
    # Simulate up to cap
    for _ in range(10):
        backoff = min(backoff * 2.0, provider.reconnect_backoff_max)
    assert backoff == 30.0


def test_twelve_data_thread_lifecycle_mocked():
    q = Queue()
    mock_connect = MagicMock()
    mock_ws = MagicMock()
    mock_connect.return_value.__enter__.return_value = mock_ws
    mock_ws.recv.side_effect = [
        json.dumps({"event": "price", "symbol": "AAPL", "price": 190.0, "day_volume": 100}),
        Exception("Simulated socket close"),
    ]

    provider = TwelveDataProvider(
        tick_queue=q,
        api_key="test_key",
        symbols=["AAPL"],
        connect_fn=mock_connect,
        reconnect_backoff_initial=0.01,
        reconnect_backoff_max=0.05,
    )

    provider.start()
    time.sleep(0.08)
    provider.stop()

    assert not provider.is_running()
