import math
from typing import Optional, Dict, Any
from app.data_feed import Tick
from app.strategies.base import Strategy, Signal


class MeanReversionStrategy(Strategy):
    """
    Mean Reversion Strategy using Bollinger Bands.
    Computes a 20-period SMA ± 2 standard deviations.
    Emits BUY when price touches or drops below the lower band.
    Emits SELL when price touches or rises above the upper band.
    """

    def __init__(self, symbol: str, params: Optional[Dict[str, Any]] = None):
        super().__init__(symbol, params, maxlen=100)
        self.period = int(self.params.get("period", 20))
        self.num_std = float(self.params.get("num_std", 2.0))
        self.current_sma: Optional[float] = None
        self.current_upper: Optional[float] = None
        self.current_lower: Optional[float] = None

    @property
    def name(self) -> str:
        return f"Bollinger_Bands_{self.period}_{self.num_std}"

    def calculate_bands(self) -> Optional[tuple[float, float, float]]:
        if len(self.prices) < self.period:
            return None

        price_slice = list(self.prices)[-self.period:]
        sma = sum(price_slice) / self.period
        variance = sum((p - sma) ** 2 for p in price_slice) / self.period
        std_dev = math.sqrt(variance)

        upper_band = round(sma + (self.num_std * std_dev), 4)
        lower_band = round(sma - (self.num_std * std_dev), 4)
        return sma, upper_band, lower_band

    def update(self, tick: Tick) -> Optional[Signal]:
        if tick.symbol != self.symbol:
            return None

        current_price = float(tick.price)
        self.prices.append(current_price)
        bands = self.calculate_bands()
        if bands is None:
            return None

        sma, upper, lower = bands
        self.current_sma = sma
        self.current_upper = upper
        self.current_lower = lower

        signal = None

        # Price touches or drops below lower band: oversold mean reversion buy opportunity
        if current_price <= lower:
            if self.last_signal_type != "BUY":
                self.last_signal_type = "BUY"
                signal = Signal(
                    symbol=self.symbol,
                    strategy_name=self.name,
                    signal_type="BUY",
                    price=tick.price,
                    timestamp=tick.timestamp,
                )
        # Price touches or rises above upper band: overbought mean reversion sell opportunity
        elif current_price >= upper:
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
            # Re-arm signal triggers if price re-crosses near the median SMA
            if abs(current_price - sma) <= 0.05 * (upper - lower + 1e-6):
                self.last_signal_type = None

        return signal

    def reset(self):
        super().reset()
        self.current_sma = None
        self.current_upper = None
        self.current_lower = None
