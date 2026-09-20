import json
import time
from decimal import Decimal
from queue import Queue
from unittest.mock import MagicMock, patch

from app.data.twelve_data import TwelveDataProvider
from app.engine.portfolio import Portfolio
from app.engine.order_executor import OrderExecutor
from app.engine.signal_engine import SignalEngine
from app.strategies.moving_average import MovingAverageCrossover


def test_mock_twelve_data_to_simulated_execution_pipeline():
    """
    End-to-end integration test:
    Mocked Twelve Data WebSocket events -> TwelveDataProvider
    -> queue.Queue -> SignalEngine -> Strategy -> OrderExecutor
    -> Simulated Portfolio.
    Validates that real-time market data flows through without any real trading.
    """
    tick_queue = Queue(maxsize=1000)
    portfolio = Portfolio(initial_cash=100000.0)
    order_executor = OrderExecutor(
        portfolio=portfolio,
        position_size_pct=0.10,
        slippage_pct=0.001,
        commission=1.0,
    )

    # Strategy: fast=2, slow=3 on AAPL
    signal_engine = SignalEngine(
        tick_queue=tick_queue,
        order_executor=order_executor,
        symbols=["AAPL"],
        strategy_factories=[
            lambda sym: MovingAverageCrossover(sym, {"fast_period": 2, "slow_period": 3})
        ],
    )

    provider = TwelveDataProvider(
        tick_queue=tick_queue,
        api_key="mock_twelve_data_key",
        symbols=["AAPL"],
    )

    # Start consumer engine
    signal_engine.start()

    try:
        # Simulate Twelve Data streaming price events
        price_events = [
            {"event": "price", "symbol": "AAPL", "price": 100.0, "day_volume": 1000, "timestamp": 1710000001},
            {"event": "price", "symbol": "AAPL", "price": 100.0, "day_volume": 1100, "timestamp": 1710000002},
            {"event": "price", "symbol": "AAPL", "price": 100.0, "day_volume": 1200, "timestamp": 1710000003},
            # Upward price breakout triggers BUY signal
            {"event": "price", "symbol": "AAPL", "price": 125.0, "day_volume": 2500, "timestamp": 1710000004},
        ]

        for ev in price_events:
            provider._handle_message(json.dumps(ev))
            time.sleep(0.05)

        # Allow consumer queue processing
        time.sleep(0.2)

        # Verify portfolio execution
        snapshot = portfolio.get_snapshot()
        assert snapshot["total_equity"] > 0
        assert "AAPL" in snapshot["positions"]
        pos = snapshot["positions"]["AAPL"]
        assert pos["quantity"] > 0
        assert pos["market_value"] > 0

        # Portfolio cash balance decreased by trade value + commission
        assert snapshot["cash_balance"] < 100000.0

        # Verify provider telemetry
        status = provider.get_status()
        assert status["provider"] == "twelve_data"
        assert status["ticks_processed"] == 4
        assert status["dropped_ticks"] == 0

    finally:
        signal_engine.stop()
