from datetime import datetime, timezone
from app.data_feed import Tick
from app.strategies.moving_average import MovingAverageCrossover
from app.strategies.rsi import RSIStrategy
from app.strategies.mean_reversion import MeanReversionStrategy


def make_tick(symbol: str, price: float) -> Tick:
    return Tick(
        symbol=symbol,
        price=price,
        volume=100,
        timestamp=datetime.now(timezone.utc),
    )


def test_moving_average_crossover_signals():
    # fast=3, slow=6
    strategy = MovingAverageCrossover("AAPL", {"fast_period": 3, "slow_period": 6})

    # Warm up with declining/flat prices: 10, 10, 10, 10, 10, 10
    for p in [10.0, 10.0, 10.0, 10.0, 10.0, 10.0]:
        sig = strategy.update(make_tick("AAPL", p))
        assert sig is None

    # Fast SMA is 10, Slow SMA is 10
    # Now sharp surge: [15, 20]
    # At 15: last 3 are [10, 10, 15] -> fast=11.67, slow last 6: [10, 10, 10, 10, 10, 15] -> slow=10.83
    # Fast crosses above slow -> BUY signal
    sig1 = strategy.update(make_tick("AAPL", 15.0))
    assert sig1 is not None
    assert sig1.signal_type == "BUY"
    assert sig1.symbol == "AAPL"

    # Feed more high prices to solidify
    strategy.update(make_tick("AAPL", 20.0))
    strategy.update(make_tick("AAPL", 20.0))

    # Now sharp drop: [5, 4, 3]
    strategy.update(make_tick("AAPL", 5.0))
    sig2 = strategy.update(make_tick("AAPL", 4.0))

    # Should emit SELL on downward crossover
    assert sig2 is not None
    assert sig2.signal_type == "SELL"


def test_rsi_strategy_signals():
    strategy = RSIStrategy("AAPL", {"period": 5, "oversold": 30.0, "overbought": 70.0})

    # Warm up: 5 + 1 = 6 ticks
    for p in [50.0, 50.0, 50.0, 50.0, 50.0, 50.0]:
        strategy.update(make_tick("AAPL", p))

    # Crash price consecutively to generate losses -> oversold RSI (< 30)
    buy_signal = None
    for p in [45.0, 40.0, 35.0, 30.0, 25.0]:
        sig = strategy.update(make_tick("AAPL", p))
        if sig and sig.signal_type == "BUY":
            buy_signal = sig
            break

    assert buy_signal is not None
    assert buy_signal.signal_type == "BUY"

    # Rally price consecutively to generate strong gains -> overbought RSI (> 70)
    sell_signal = None
    for p in [35.0, 45.0, 55.0, 65.0, 75.0, 85.0]:
        sig = strategy.update(make_tick("AAPL", p))
        if sig and sig.signal_type == "SELL":
            sell_signal = sig
            break

    assert sell_signal is not None
    assert sell_signal.signal_type == "SELL"


def test_mean_reversion_bollinger_bands():
    # 10 period, 2 std dev
    strategy = MeanReversionStrategy("AAPL", {"period": 10, "num_std": 2.0})

    # Feed steady prices around 100
    base_prices = [100.0, 101.0, 99.0, 100.0, 100.5, 99.5, 100.0, 100.2, 99.8, 100.0]
    for p in base_prices:
        strategy.update(make_tick("AAPL", p))

    # A price drop well below lower band (e.g. 95.0)
    sig_buy = strategy.update(make_tick("AAPL", 95.0))
    assert sig_buy is not None
    assert sig_buy.signal_type == "BUY"

    # Feed prices returning up and then spiking way above upper band (e.g. 110.0)
    for p in [100.0, 100.0, 101.0, 100.0, 100.0]:
        strategy.update(make_tick("AAPL", p))

    sig_sell = strategy.update(make_tick("AAPL", 112.0))
    assert sig_sell is not None
    assert sig_sell.signal_type == "SELL"
