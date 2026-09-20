from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.models import Base, SignalModel, TickModel, OrderModel
from app.engine.portfolio import Portfolio
from app.ai_assistant import ChartBotAssistant, AITradingAssistant


def setup_test_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return Session


def test_chart_bot_explain_signal():
    Session = setup_test_db()
    with Session() as session:
        sig = SignalModel(
            id=1,
            symbol="AAPL",
            strategy_name="MA_Crossover_5_20",
            signal_type="BUY",
            price=150.25,
            timestamp=datetime.now(timezone.utc),
        )
        session.add(sig)

        # Seed 25 ticks to satisfy 20-period SMA
        for i in range(25):
            session.add(TickModel(
                symbol="AAPL",
                price=140.0 + i * 0.5,
                volume=1000,
                timestamp=datetime.now(timezone.utc),
            ))
        session.commit()

    bot = ChartBotAssistant(session_factory=Session)
    explanation = bot.explain_signal(signal_id=1)

    assert "[ChartBot]" in explanation
    assert "Signal #1 (BUY AAPL @ $150.25)" in explanation
    assert "Moving Average Crossover" in explanation
    assert "SMA" in explanation
    assert "bullish entry signal" in explanation


def test_chart_bot_price_and_trend_analysis():
    Session = setup_test_db()
    with Session() as session:
        for p in [150.0, 151.0, 152.5, 154.0, 155.0]:
            session.add(TickModel(
                symbol="AAPL",
                price=p,
                volume=5000,
                timestamp=datetime.now(timezone.utc),
            ))
        session.commit()

    portfolio = Portfolio(initial_cash=90000.0, session_factory=Session)
    portfolio.apply_fill("AAPL", "BUY", 20, 150.0, commission=1.0, persist=False)

    bot = ChartBotAssistant(portfolio=portfolio, session_factory=Session)
    answer = bot.answer_question("What is the price and trend of AAPL?")

    assert "AAPL Live Chart & Technical Analysis" in answer
    assert "$155.00" in answer
    assert "Bullish" in answer
    assert "20 shares" in answer
    assert "Support (Recent Low)" in answer
    assert "Resistance (Recent High)" in answer


def test_chart_bot_indicator_inquiry():
    bot = ChartBotAssistant()

    rsi_ans = bot.answer_question("Explain the RSI indicator")
    assert "Relative Strength Index" in rsi_ans
    assert "30.0" in rsi_ans
    assert "70.0" in rsi_ans

    boll_ans = bot.answer_question("How do Bollinger Bands work?")
    assert "Bollinger Bands" in boll_ans
    assert "standard deviations" in boll_ans
    assert "mean-reversion" in boll_ans

    ma_ans = bot.answer_question("What is Moving Average Crossover?")
    assert "Moving Average" in ma_ans
    assert "Fast MA" in ma_ans
    assert "Slow MA" in ma_ans


def test_chart_bot_portfolio_metrics():
    Session = setup_test_db()
    portfolio = Portfolio(initial_cash=100000.0, session_factory=Session)
    portfolio.apply_fill("MSFT", "BUY", 10, 300.0, commission=1.0, persist=False)

    bot = ChartBotAssistant(portfolio=portfolio, session_factory=Session)

    equity_ans = bot.answer_question("What is my total portfolio equity and cash?")
    assert "$100,000.00" in equity_ans or "$99,999.00" in equity_ans
    assert "Cash Balance" in equity_ans

    pos_ans = bot.answer_question("What open positions do I currently have?")
    assert "MSFT" in pos_ans
    assert "10 shares" in pos_ans

    pnl_ans = bot.answer_question("What is my P&L?")
    assert "P&L Performance Overview" in pnl_ans
    assert "Realized P&L" in pnl_ans


def test_chart_bot_greetings_and_help():
    bot = ChartBotAssistant()
    greet_ans = bot.answer_question("Hello, who are you?")
    assert "Hello! I'm ChartBot" in greet_ans
    assert "price and trend of AAPL" in greet_ans


def test_chart_bot_market_data_telemetry():
    bot = ChartBotAssistant()
    telemetry_ans = bot.answer_question("What market data provider are you using?")
    assert "Market Data Telemetry" in telemetry_ans
    assert "Twelve Data" in telemetry_ans


def test_chart_bot_set_api_key_compatibility():
    bot = ChartBotAssistant()
    assert bot.is_bot_active()
    assert not bot.is_gemini_active()

    success, msg = bot.set_api_key("some_key")
    assert success
    assert "locally" in msg
