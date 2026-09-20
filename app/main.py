import os
import re
import asyncio
import logging
from contextlib import asynccontextmanager
from queue import Queue
from typing import Dict, Any, List, Optional, Union

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.db import init_db, get_db, db_session, SessionLocal
from app.models import OrderModel, SignalModel, TickModel, PortfolioSnapshotModel
from app.data_feed import MarketDataFeed
from app.engine.portfolio import Portfolio
from app.engine.order_executor import OrderExecutor
from app.engine.signal_engine import SignalEngine
from app.strategies.moving_average import MovingAverageCrossover
from app.strategies.rsi import RSIStrategy
from app.strategies.mean_reversion import MeanReversionStrategy
from app.ws_manager import ws_manager
from app.ai_assistant import AITradingAssistant

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("trading-engine")

# Global components
tick_queue: Queue = Queue(maxsize=settings.MARKET_DATA_QUEUE_SIZE)
portfolio = Portfolio(initial_cash=settings.INITIAL_CASH)
order_executor = OrderExecutor(
    portfolio=portfolio,
    position_size_pct=settings.POSITION_SIZE_CASH_PCT,
    slippage_pct=settings.SLIPPAGE_PCT,
    commission=settings.COMMISSION_FLAT,
    max_position_equity_pct=settings.MAX_POSITION_EQUITY_PCT,
)
data_feed = MarketDataFeed(
    tick_queue=tick_queue,
    mode=settings.MARKET_DATA_MODE,
    symbols=settings.SYMBOLS,
    batch_size=settings.BATCH_INSERT_SIZE,
    max_queue_size=settings.MARKET_DATA_QUEUE_SIZE,
)
signal_engine = SignalEngine(
    tick_queue=tick_queue,
    order_executor=order_executor,
    symbols=settings.SYMBOLS,
)
ai_assistant = AITradingAssistant(portfolio=portfolio, data_feed=data_feed)

broadcast_task = None


async def live_broadcast_loop():
    """Periodically pushes updates over WebSockets to connected dashboards."""
    logger.info("Live WebSocket broadcast loop initiated.")
    while True:
        try:
            if ws_manager.active_connections:
                # Get latest ticks from feed memory or fallback to database
                latest_ticks = data_feed.get_latest_ticks()
                with db_session() as session:
                    if not latest_ticks:
                        for sym in settings.SYMBOLS:
                            t = (
                                session.query(TickModel)
                                .filter(TickModel.symbol == sym)
                                .order_by(TickModel.timestamp.desc())
                                .first()
                            )
                            if t:
                                latest_ticks[sym] = t.to_dict()

                    # Gather latest 15 signals
                    sigs = (
                        session.query(SignalModel)
                        .order_by(SignalModel.timestamp.desc())
                        .limit(15)
                        .all()
                    )
                    signals_data = [s.to_dict() for s in sigs]

                    # Gather latest 15 orders
                    ords = (
                        session.query(OrderModel)
                        .order_by(OrderModel.timestamp.desc())
                        .limit(15)
                        .all()
                    )
                    orders_data = [o.to_dict() for o in ords]

                # Current portfolio snapshot
                snap = portfolio.get_snapshot()

                payload = {
                    "type": "market_update",
                    "ticks": latest_ticks,
                    "portfolio": snap,
                    "signals": signals_data,
                    "orders": orders_data,
                    "market_data": data_feed.get_status(),
                }
                await ws_manager.broadcast(payload)
        except Exception as e:
            logger.error("Error in broadcast loop: %s", e)

        await asyncio.sleep(1.0)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Initializing trading engine database...")
    init_db()

    logger.info("Starting Market Data Feed and Signal Engine background threads...")
    data_feed.start()
    signal_engine.start()

    global broadcast_task
    broadcast_task = asyncio.create_task(live_broadcast_loop())

    yield

    # Shutdown
    logger.info("Shutting down trading engine...")
    if broadcast_task:
        broadcast_task.cancel()
    data_feed.stop()
    signal_engine.stop()
    logger.info("Trading engine shutdown complete.")


app = FastAPI(
    title="Algorithmic Trading & Market Data Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Mount static directory
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


# Pydantic Schemas for API
class AskRequest(BaseModel):
    question: str


# Endpoints
@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "data_feed_alive": data_feed.is_alive(),
        "signal_engine_alive": signal_engine.is_alive(),
        "market_data_mode": data_feed.mode,
        "market_data_provider": data_feed.provider.provider_name,
        "market_data_status": data_feed.get_status(),
    }


@app.get("/api/market-data/symbols")
def get_market_data_symbols():
    return {
        "symbols": list(data_feed.symbols),
        "count": len(data_feed.symbols),
        "mode": data_feed.mode,
    }


@app.get("/api/market-data/status")
def get_market_data_status():
    return {
        "status": "ok",
        "market_data": data_feed.get_status(),
    }


class MarketDataConfigRequest(BaseModel):
    mode: str = "live"
    api_key: Optional[str] = None
    symbols: Optional[Union[List[str], str]] = None


@app.post("/api/market-data/set-config")
def set_market_data_config(req: MarketDataConfigRequest):
    symbols_list = None
    if req.symbols:
        if isinstance(req.symbols, str):
            symbols_list = [s.strip().upper() for s in req.symbols.split(",") if s.strip()]
        else:
            symbols_list = [s.strip().upper() for s in req.symbols if s.strip()]

    try:
        success, message = data_feed.switch_provider(
            new_mode=req.mode,
            api_key=req.api_key,
            symbols=symbols_list,
        )
    except Exception as e:
        logger.error("Failed switching market data provider: %s", e)
        raise HTTPException(status_code=400, detail=str(e))

    # Dynamically update SignalEngine strategy subscriptions if symbols changed
    if symbols_list:
        for sym in symbols_list:
            if sym not in signal_engine.strategies:
                signal_engine.register_strategy(sym, MovingAverageCrossover(symbol=sym))
                signal_engine.register_strategy(sym, RSIStrategy(symbol=sym))
                signal_engine.register_strategy(sym, MeanReversionStrategy(symbol=sym))

    # Persist updated configuration to .env (skip in automated test suite)
    if not os.environ.get("TESTING"):
        try:
            env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            if os.path.exists(env_path):
                with open(env_path, "r") as f:
                    content = f.read()

                content = re.sub(r"MARKET_DATA_MODE=.*", f"MARKET_DATA_MODE={data_feed.mode}", content)
                if req.api_key is not None and req.api_key.strip():
                    content = re.sub(r"TWELVE_DATA_API_KEY=.*", f"TWELVE_DATA_API_KEY={req.api_key.strip()}", content)
                if symbols_list:
                    syms_str = ",".join(symbols_list)
                    content = re.sub(r"SYMBOLS=.*", f"SYMBOLS={syms_str}", content)

                with open(env_path, "w") as f:
                    f.write(content)
        except Exception as e:
            logger.warning("Could not persist market data config to .env: %s", e)

    return {
        "success": success,
        "message": message,
        "mode": data_feed.mode,
        "provider": data_feed.provider.provider_name,
        "status": data_feed.get_status(),
        "symbols": list(data_feed.symbols),
    }



@app.get("/")
def serve_dashboard():
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Trading engine running. static/index.html not found."}


@app.get("/api/portfolio")
def get_portfolio():
    return portfolio.get_snapshot()


@app.get("/api/trades")
def get_trades(limit: int = 50):
    with db_session() as session:
        orders = (
            session.query(OrderModel)
            .order_by(OrderModel.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [o.to_dict() for o in orders]


@app.get("/api/signals")
def get_signals(limit: int = 50):
    with db_session() as session:
        signals = (
            session.query(SignalModel)
            .order_by(SignalModel.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [s.to_dict() for s in signals]


@app.get("/api/strategies")
def get_strategies():
    strategies_info = []
    for sym, strats in signal_engine.strategies.items():
        for s in strats:
            strategies_info.append({
                "symbol": sym,
                "strategy_name": s.name,
                "params": s.params,
                "class": s.__class__.__name__,
            })
    return {
        "active_strategies_count": len(strategies_info),
        "strategies": strategies_info,
    }


class SetKeyRequest(BaseModel):
    api_key: str


@app.get("/api/assistant/status")
def get_assistant_status():
    return {
        "bot_name": getattr(ai_assistant, "bot_name", "ChartBot"),
        "active": True,
        "type": "Built-in Chart & Quantitative Assistant",
        "version": getattr(ai_assistant, "version", "1.0"),
        "gemini_active": False,
        "claude_active": False,
        "model": "ChartBot v1.0",
    }


@app.post("/api/assistant/set-key")
def set_assistant_key(req: SetKeyRequest):
    success, message = ai_assistant.set_api_key(req.api_key)
    return {
        "success": success,
        "message": message,
        "bot_name": getattr(ai_assistant, "bot_name", "ChartBot"),
        "active": True,
        "gemini_active": False,
        "claude_active": False,
    }


@app.post("/api/assistant/ask")
def ask_assistant(req: AskRequest):
    if not req.question or not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
    answer = ai_assistant.answer_question(req.question.strip())
    return {"question": req.question, "answer": answer}


@app.get("/api/assistant/explain/{signal_id}")
def explain_signal(signal_id: int):
    explanation = ai_assistant.explain_signal(signal_id)
    return {"signal_id": signal_id, "explanation": explanation}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        # Send immediate initial state
        snap = portfolio.get_snapshot()
        latest_ticks = data_feed.get_latest_ticks()
        with db_session() as session:
            sigs = session.query(SignalModel).order_by(SignalModel.timestamp.desc()).limit(15).all()
            signals_data = [s.to_dict() for s in sigs]
            ords = session.query(OrderModel).order_by(OrderModel.timestamp.desc()).limit(15).all()
            orders_data = [o.to_dict() for o in ords]

        await websocket.send_json({
            "type": "initial_state",
            "portfolio": snap,
            "ticks": latest_ticks,
            "signals": signals_data,
            "orders": orders_data,
            "market_data": data_feed.get_status(),
        })
        while True:
            # Keep connection open and receive any client ping
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug("WebSocket error: %s", e)
        ws_manager.disconnect(websocket)
