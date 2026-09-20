import time
from queue import Queue
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base
from app.data_feed import MarketDataFeed
from app.engine.portfolio import Portfolio
from app.engine.order_executor import OrderExecutor
from app.engine.signal_engine import SignalEngine
from app.strategies.moving_average import MovingAverageCrossover
from app.strategies.rsi import RSIStrategy
from app.strategies.mean_reversion import MeanReversionStrategy


def test_full_pipeline_integration_100_ticks():
    # Setup clean in-memory test database with StaticPool for cross-thread memory sharing
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    tick_q = Queue()
    portfolio = Portfolio(initial_cash=100000.0, session_factory=TestSession)
    order_executor = OrderExecutor(
        portfolio=portfolio,
        position_size_pct=0.10,
        slippage_pct=0.0005,
        commission=1.00,
        max_position_equity_pct=0.40,
        session_factory=TestSession,
    )

    # Use fast-trigger strategies to ensure signals fire within 100 ticks
    fast_factories = [
        lambda sym: MovingAverageCrossover(sym, {"fast_period": 3, "slow_period": 6}),
        lambda sym: RSIStrategy(sym, {"period": 5, "oversold": 40.0, "overbought": 60.0}),
        lambda sym: MeanReversionStrategy(sym, {"period": 8, "num_std": 1.0}),
    ]

    signal_engine = SignalEngine(
        tick_queue=tick_q,
        order_executor=order_executor,
        symbols=["AAPL", "TSLA"],
        session_factory=TestSession,
        strategy_factories=fast_factories,
    )

    signals_captured = []
    signal_engine.on_signal_callback = lambda sig: signals_captured.append(sig)

    # Market feed with volatility to stimulate crossovers
    data_feed = MarketDataFeed(
        tick_queue=tick_q,
        symbols=["AAPL", "TSLA"],
        volatility=0.03,
        batch_size=10,
        session_factory=TestSession,
        persist_to_db=True,
    )

    # Start signal engine consumer thread
    signal_engine.start()

    # Generate 100 ticks directly onto the queue
    for _ in range(50):
        for sym in ["AAPL", "TSLA"]:
            tick = data_feed.generate_next_tick(sym)
            tick_q.put(tick)

    # Wait for queue to be fully consumed by the consumer thread
    tick_q.join()

    # Stop thread gracefully
    signal_engine.stop(timeout=2.0)
    assert not signal_engine.is_alive()

    # Verify signals generated
    assert len(signals_captured) >= 1, f"Expected at least 1 signal, got {len(signals_captured)}"

    # Verify portfolio state consistency
    snap = portfolio.get_snapshot()
    assert snap["cash_balance"] > 0
    assert snap["total_equity"] > 0

    positions_value = sum(p["market_value"] for p in snap["positions"].values())
    expected_equity = round(snap["cash_balance"] + positions_value, 2)
    assert abs(snap["total_equity"] - expected_equity) < 0.05
