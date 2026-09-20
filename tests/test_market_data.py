import pytest
from datetime import datetime, timezone
from decimal import Decimal
from queue import Queue

from app.data.base import Tick, validate_tick, MarketDataProvider


class DummyProvider(MarketDataProvider):
    @property
    def provider_name(self) -> str:
        return "dummy"

    @property
    def mode_name(self) -> str:
        return "dummy_mode"

    def start(self):
        pass

    def stop(self, timeout: float = 3.0):
        pass

    def is_running(self) -> bool:
        return True

    def subscribe(self, symbols):
        self.symbols.extend(symbols)


def test_tick_normalization_and_to_dict():
    now = datetime.now(timezone.utc)
    tick = Tick(
        symbol="AAPL",
        price=185.50,
        volume=1500,
        timestamp=now,
        source="twelve_data",
    )

    assert tick.symbol == "AAPL"
    assert isinstance(tick.price, Decimal)
    assert tick.price == Decimal("185.5")
    assert isinstance(tick.volume, Decimal)
    assert tick.volume == Decimal("1500")
    assert tick.source == "twelve_data"

    data = tick.to_dict()
    assert data["symbol"] == "AAPL"
    assert data["price"] == 185.5
    assert data["volume"] == 1500.0
    assert data["source"] == "twelve_data"
    assert data["timestamp"] == now.isoformat()


def test_validate_tick_valid():
    tick = Tick(
        symbol="MSFT",
        price=Decimal("420.00"),
        volume=Decimal("100"),
        timestamp=datetime.now(timezone.utc),
        source="simulation",
    )
    is_valid, err = validate_tick(tick)
    assert is_valid is True
    assert err is None


def test_validate_tick_empty_or_whitespace_symbol():
    tick = Tick(
        symbol="   ",
        price=Decimal("100"),
        source="simulation",
    )
    is_valid, err = validate_tick(tick)
    assert is_valid is False
    assert "Tick symbol must be a non-empty string" in err


def test_validate_tick_non_positive_price():
    tick_zero = Tick(
        symbol="TSLA",
        price=Decimal("0.0"),
        source="simulation",
    )
    is_valid, err = validate_tick(tick_zero)
    assert is_valid is False
    assert "positive" in err

    tick_neg = Tick(
        symbol="TSLA",
        price=Decimal("-10.5"),
        source="simulation",
    )
    is_valid, err = validate_tick(tick_neg)
    assert is_valid is False
    assert "positive" in err


def test_validate_tick_negative_volume():
    tick = Tick(
        symbol="GOOGL",
        price=Decimal("150.0"),
        volume=Decimal("-50"),
        source="simulation",
    )
    is_valid, err = validate_tick(tick)
    assert is_valid is False
    assert "negative" in err


def test_validate_tick_missing_source():
    tick = Tick(
        symbol="NVDA",
        price=Decimal("120.0"),
        source="",
    )
    is_valid, err = validate_tick(tick)
    assert is_valid is False
    assert "source" in err


def test_provider_push_tick_queue_overflow():
    # Bounded queue with maxsize=2
    q = Queue(maxsize=2)
    provider = DummyProvider(tick_queue=q, symbols=["AAPL"], max_queue_size=2)

    tick1 = Tick("AAPL", Decimal("100.0"), source="dummy")
    tick2 = Tick("AAPL", Decimal("101.0"), source="dummy")
    tick3 = Tick("AAPL", Decimal("102.0"), source="dummy")

    assert provider.push_tick(tick1) is True
    assert provider.push_tick(tick2) is True
    # Queue is full, tick3 must be dropped safely
    assert provider.push_tick(tick3) is False
    assert provider.dropped_ticks == 1
    assert provider.ticks_received == 3
    assert provider.ticks_processed == 2


def test_provider_telemetry_get_status():
    q = Queue(maxsize=100)
    provider = DummyProvider(tick_queue=q, symbols=["AAPL", "MSFT"], max_queue_size=100)

    tick = Tick("AAPL", Decimal("150.0"), source="dummy")
    provider.push_tick(tick)

    status = provider.get_status()
    assert status["mode"] == "dummy_mode"
    assert status["provider"] == "dummy"
    assert status["symbols"] == 2
    assert "AAPL" in status["symbols_list"]
    assert status["queue_size"] == 1
    assert status["max_queue_size"] == 100
    assert status["ticks_processed"] == 1
    assert status["dropped_ticks"] == 0
    assert status["last_tick"] is not None
