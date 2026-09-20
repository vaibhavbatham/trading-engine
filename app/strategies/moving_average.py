from typing import Optional, Dict, Any
from app.data_feed import Tick
from app.strategies.base import Strategy, Signal


class MovingAverageCrossover(Strategy):
    """
    Dual Moving Average Crossover Strategy.
    Tracks a fast SMA (e.g. 5-period) and slow SMA (e.g. 20-period).
    Emits BUY when fast crosses above slow, SELL when it crosses below.
    """

    def __init__(self, symbol: str, params: Optional[Dict[str, Any]] = None):
        super().__init__(symbol, params, maxlen=100)
        self.fast_period = int(self.params.get("fast_period", 5))
        self.slow_period = int(self.params.get("slow_period", 20))
        self.prev_fast: Optional[float] = None
        self.prev_slow: Optional[float] = None

    @property
    def name(self) -> str:
        return f"MA_Crossover_{self.fast_period}_{self.slow_period}"

    def update(self, tick: Tick) -> Optional[Signal]:
        if tick.symbol != self.symbol:
            return None

        self.prices.append(float(tick.price))

        if len(self.prices) < self.slow_period:
            return None

        price_list = list(self.prices)
        fast_sma = sum(price_list[-self.fast_period:]) / self.fast_period
        slow_sma = sum(price_list[-self.slow_period:]) / self.slow_period

        signal = None

        if self.prev_fast is not None and self.prev_slow is not None:
            # Bullish crossover: fast crosses strictly above slow
            if self.prev_fast <= self.prev_slow and fast_sma > slow_sma:
                if self.last_signal_type != "BUY":
                    self.last_signal_type = "BUY"
                    signal = Signal(
                        symbol=self.symbol,
                        strategy_name=self.name,
                        signal_type="BUY",
                        price=tick.price,
                        timestamp=tick.timestamp,
                    )
            # Bearish crossover: fast crosses strictly below slow
            elif self.prev_fast >= self.prev_slow and fast_sma < slow_sma:
                if self.last_signal_type != "SELL":
                    self.last_signal_type = "SELL"
                    signal = Signal(
                        symbol=self.symbol,
                        strategy_name=self.name,
                        signal_type="SELL",
                        price=tick.price,
                        timestamp=tick.timestamp,
                    )

        self.prev_fast = fast_sma
        self.prev_slow = slow_sma
        return signal

    def reset(self):
        super().reset()
        self.prev_fast = None
        self.prev_slow = None
