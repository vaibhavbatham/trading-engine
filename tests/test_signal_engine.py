import time
from queue import Queue
from datetime import datetime, timezone
from app.data_feed import Tick
from app.engine.portfolio import Portfolio
from app.engine.order_executor import OrderExecutor
from app.engine.signal_engine import SignalEngine
from app.strategies.moving_average import MovingAverageCrossover


def test_signal_engine_processing():
    q = Queue()
    portfolio = Portfolio(initial_cash=100000.0)
    executor = OrderExecutor(portfolio=portfolio, position_size_pct=0.10)

    # Use a fast MA strategy factory for testing: fast=2, slow=4
    engine = SignalEngine(
        tick_queue=q,
        order_executor=executor,
        symbols=["AAPL"],
        strategy_factories=[lambda sym: MovingAverageCrossover(sym, {"fast_period": 2, "slow_period": 4})],
    )

    signals_captured = []
    engine.on_signal_callback = lambda sig: signals_captured.append(sig)

    # Feed ticks to trigger crossover
    # 4 flat ticks: 10, 10, 10, 10
    # Then sudden jump: 20 -> triggers BUY
    prices = [10.0, 10.0, 10.0, 10.0, 20.0]
    for p in prices:
        tick = Tick("AAPL", p, 100, datetime.now(timezone.utc))
        engine.process_tick(tick)

    assert len(signals_captured) >= 1
    assert signals_captured[0].signal_type == "BUY"
    assert signals_captured[0].symbol == "AAPL"

    # Verify order executor received and filled the trade
    pos = portfolio.get_position("AAPL")
    assert pos is not None
    assert pos.quantity > 0


def test_signal_engine_thread_lifecycle():
    q = Queue()
    portfolio = Portfolio(initial_cash=100000.0)
    executor = OrderExecutor(portfolio=portfolio)
    engine = SignalEngine(tick_queue=q, order_executor=executor, symbols=["GOOGL"])

    engine.start()
    assert engine.is_alive()

    # Put a dummy tick
    q.put(Tick("GOOGL", 150.0, 100, datetime.now(timezone.utc)))
    time.sleep(0.1)

    engine.stop()
    assert not engine.is_alive()
