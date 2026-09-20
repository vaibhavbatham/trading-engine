import time
from queue import Queue
from datetime import datetime
from app.data_feed import MarketDataFeed, Tick


def test_tick_generation_structure():
    q = Queue()
    feed = MarketDataFeed(tick_queue=q, symbols=["AAPL"], persist_to_db=False)
    tick = feed.generate_next_tick("AAPL")

    assert isinstance(tick, Tick)
    assert tick.symbol == "AAPL"
    assert tick.price > 0
    assert 50 <= tick.volume <= 500
    assert isinstance(tick.timestamp, datetime)


def test_tick_queue_receives_items():
    q = Queue()
    feed = MarketDataFeed(
        tick_queue=q,
        symbols=["AAPL", "MSFT"],
        interval=0.05,
        persist_to_db=False,
    )

    feed.start()
    time.sleep(0.2)
    feed.stop()

    assert not feed.is_alive()
    assert not q.empty()

    ticks = []
    while not q.empty():
        ticks.append(q.get())

    symbols = {t.symbol for t in ticks}
    assert "AAPL" in symbols
    assert "MSFT" in symbols
    assert len(ticks) >= 2


def test_random_walk_bounds():
    q = Queue()
    initial_price = 100.0
    feed = MarketDataFeed(
        tick_queue=q,
        symbols=["AAPL"],
        initial_prices={"AAPL": initial_price},
        volatility=0.002,
        persist_to_db=False,
    )

    prices = []
    for _ in range(100):
        t = feed.generate_next_tick("AAPL")
        prices.append(t.price)
        assert t.price > 0.0

    # Under 100 steps with 0.2% volatility, price should comfortably stay within [70, 140]
    assert 70.0 < prices[-1] < 140.0


def test_data_feed_switch_provider_runtime():
    q = Queue()
    feed = MarketDataFeed(tick_queue=q, symbols=["AAPL"], mode="simulation", persist_to_db=False)
    assert feed.mode == "simulation"
    assert feed.provider.provider_name == "simulator"

    # Switch to live mode
    success, msg = feed.switch_provider(new_mode="live", api_key="td_test_key_456", symbols=["AAPL", "NVDA"])
    assert success
    assert feed.mode == "live"
    assert feed.provider.provider_name == "twelve_data"
    assert feed.symbols == ["AAPL", "NVDA"]

    # Switch back to simulation mode
    success2, msg2 = feed.switch_provider(new_mode="simulation")
    assert success2
    assert feed.mode == "simulation"
    assert feed.provider.provider_name == "simulator"

