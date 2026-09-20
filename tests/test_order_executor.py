from datetime import datetime, timezone
from app.engine.portfolio import Portfolio
from app.engine.order_executor import OrderExecutor
from app.strategies.base import Signal


def make_signal(symbol: str, side: str, price: float) -> Signal:
    return Signal(
        symbol=symbol,
        strategy_name="TestStrategy",
        signal_type=side,
        price=price,
        timestamp=datetime.now(timezone.utc),
    )


def test_order_executor_buy_and_slippage():
    portfolio = Portfolio(initial_cash=100000.0)
    executor = OrderExecutor(
        portfolio=portfolio,
        position_size_pct=0.10,  # 10% of 100,000 = 10,000 spend
        slippage_pct=0.001,      # 0.1% slippage
        commission=2.00,
        max_position_equity_pct=0.30,
    )

    # Signal: BUY AAPL @ 100.0
    # Expected fill price: 100.0 * 1.001 = 100.10
    # Expected qty: floor(10,000 / 100) = 100 shares
    signal = make_signal("AAPL", "BUY", 100.0)
    res = executor.execute_signal(signal)

    assert res["status"] == "FILLED"
    assert res["price"] == 100.10
    assert res["quantity"] == 100.0
    assert res["commission"] == 2.00

    pos = portfolio.get_position("AAPL")
    assert pos.quantity == 100.0


def test_order_executor_risk_limit_rejection():
    # Only allow 15% equity per symbol
    portfolio = Portfolio(initial_cash=10000.0)
    executor = OrderExecutor(
        portfolio=portfolio,
        position_size_pct=0.50,  # Target spend 50% = 5000 -> 50% > 15% limit
        max_position_equity_pct=0.15,
    )

    signal = make_signal("TSLA", "BUY", 100.0)
    res = executor.execute_signal(signal)

    assert res["status"] == "REJECTED"
    assert "Risk limit exceeded" in res["reason"]
    assert portfolio.get_position("TSLA") is None


def test_order_executor_sell_unheld_stock():
    portfolio = Portfolio(initial_cash=50000.0)
    executor = OrderExecutor(portfolio=portfolio)

    signal = make_signal("AMZN", "SELL", 150.0)
    res = executor.execute_signal(signal)

    assert res["status"] == "REJECTED"
    assert "No long position held" in res["reason"]
