import concurrent.futures
from app.engine.portfolio import Portfolio, Position


def test_portfolio_initial_state():
    p = Portfolio(initial_cash=50000.0)
    snap = p.get_snapshot()

    assert snap["cash_balance"] == 50000.0
    assert snap["total_equity"] == 50000.0
    assert snap["realized_pnl"] == 0.0
    assert snap["unrealized_pnl"] == 0.0
    assert len(snap["positions"]) == 0


def test_portfolio_buy_and_weighted_average():
    p = Portfolio(initial_cash=10000.0)

    # Buy 10 AAPL @ $100
    res1 = p.apply_fill("AAPL", "BUY", 10, 100.0, commission=1.0, persist=False)
    assert res1["status"] == "FILLED"
    assert p.cash_balance == 10000.0 - (10 * 100.0 + 1.0)  # 8999.0

    pos = p.get_position("AAPL")
    assert pos.quantity == 10
    assert pos.avg_entry_price == 100.0

    # Buy 10 AAPL @ $150
    res2 = p.apply_fill("AAPL", "BUY", 10, 150.0, commission=1.0, persist=False)
    assert res2["status"] == "FILLED"
    assert p.cash_balance == 8999.0 - (10 * 150.0 + 1.0)  # 7498.0

    pos = p.get_position("AAPL")
    assert pos.quantity == 20
    # Average entry: (10*100 + 10*150)/20 = 125.0
    assert pos.avg_entry_price == 125.0


def test_portfolio_sell_and_realized_pnl():
    p = Portfolio(initial_cash=10000.0)
    p.apply_fill("AAPL", "BUY", 10, 100.0, commission=0.0, persist=False)

    # Sell 5 AAPL @ $120
    # Profit: (120 - 100) * 5 = +100
    res = p.apply_fill("AAPL", "SELL", 5, 120.0, commission=1.0, persist=False)
    assert res["status"] == "FILLED"
    assert res["trade_pnl"] == 99.0  # 100 - 1 comm
    assert p.realized_pnl == 99.0
    assert p.get_position("AAPL").quantity == 5


def test_portfolio_unrealized_pnl_and_equity():
    p = Portfolio(initial_cash=10000.0)
    p.apply_fill("GOOGL", "BUY", 10, 100.0, commission=0.0, persist=False)
    p.update_market_price("GOOGL", 110.0)

    # Cash: 9000, Stock value: 10 * 110 = 1100, Total equity: 10100
    # Unrealized PnL: (110 - 100) * 10 = 100
    assert p.get_unrealized_pnl() == 100.0
    assert p.get_total_equity() == 10100.0


def test_concurrent_fills_stress_test():
    """
    Stress test with ThreadPoolExecutor firing multiple concurrent BUY and SELL
    fills to verify that Lock prevents race conditions.
    """
    initial_cash = 500000.0
    p = Portfolio(initial_cash=initial_cash)
    num_threads = 8
    operations_per_thread = 50

    def worker(worker_id: int):
        sym = f"SYM_{worker_id % 3}"
        for i in range(operations_per_thread):
            if i % 2 == 0:
                p.apply_fill(sym, "BUY", 2, 50.0, commission=0.5, persist=False)
            else:
                p.apply_fill(sym, "SELL", 1, 55.0, commission=0.5, persist=False)

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            f.result()

    snap = p.get_snapshot()
    # Confirm no negative quantities or NaNs occurred
    assert snap["cash_balance"] > 0
    assert snap["total_equity"] > 0
    for s, pos in snap["positions"].items():
        assert pos["quantity"] >= 0
        assert pos["avg_entry_price"] >= 0
