from typing import Optional, Dict, Any
from app.data_feed import Tick
from app.strategies.base import Strategy, Signal


class RSIStrategy(Strategy):
    """
    Relative Strength Index (RSI) Strategy.
    Computes a 14-period RSI.
    Emits BUY when RSI < 30 (oversold condition).
    Emits SELL when RSI > 70 (overbought condition).
    """

    def __init__(self, symbol: str, params: Optional[Dict[str, Any]] = None):
        super().__init__(symbol, params, maxlen=100)
        self.period = int(self.params.get("period", 14))
        self.oversold = float(self.params.get("oversold", 30.0))
        self.overbought = float(self.params.get("overbought", 70.0))
        self.current_rsi: Optional[float] = None

    @property
    def name(self) -> str:
        return f"RSI_{self.period}"

    def calculate_rsi(self) -> Optional[float]:
        if len(self.prices) < self.period + 1:
            return None

        price_slice = list(self.prices)[-(self.period + 1):]
        gains = []
        losses = []

        for i in range(1, len(price_slice)):
            diff = price_slice[i] - price_slice[i - 1]
            if diff > 0:
                gains.append(diff)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(abs(diff))

        avg_gain = sum(gains) / self.period
        avg_loss = sum(losses) / self.period

        if avg_loss == 0.0:
            return 100.0
        if avg_gain == 0.0:
            return 0.0

        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return round(rsi, 2)

    def update(self, tick: Tick) -> Optional[Signal]:
        if tick.symbol != self.symbol:
            return None

        self.prices.append(float(tick.price))
        rsi = self.calculate_rsi()
        if rsi is None:
            return None

        self.current_rsi = rsi
        signal = None

        if rsi < self.oversold:
            if self.last_signal_type != "BUY":
                self.last_signal_type = "BUY"
                signal = Signal(
                    symbol=self.symbol,
                    strategy_name=self.name,
                    signal_type="BUY",
                    price=tick.price,
                    timestamp=tick.timestamp,
                )
        elif rsi > self.overbought:
            if self.last_signal_type != "SELL":
                self.last_signal_type = "SELL"
                signal = Signal(
                    symbol=self.symbol,
                    strategy_name=self.name,
                    signal_type="SELL",
                    price=tick.price,
                    timestamp=tick.timestamp,
                )
        else:
            # When price returns to neutral band (30 <= rsi <= 70), allow new signals
            if 40 <= rsi <= 60:
                self.last_signal_type = None

        return signal

    def reset(self):
        super().reset()
        self.current_rsi = None
