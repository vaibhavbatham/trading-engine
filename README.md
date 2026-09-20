# Algorithmic Trading & Market Data Platform (`trading-engine`)

A high-performance, real-time algorithmic trading and market data simulation platform built with **Python 3.11+**, **FastAPI**, multi-threaded **Producer-Consumer** architecture (`queue.Queue`), **SQLAlchemy** (PostgreSQL / SQLite), live **WebSockets** with **Chart.js**, and a **Google Gemini AI** trading assistant.

---

## 🏛️ Architecture Overview

```mermaid
flowchart TD
    subgraph Market Data Layer [Pluggable Data Providers]
        TD[Twelve Data WebSocket API\nwss://ws.twelvedata.com] -->|Live Quotes| MDF[MarketDataFeed Producer]
        SIM[SimulationProvider\nBrownian Motion] -.->|Synthetic Ticks| MDF
        REP[HistoricalReplayProvider\nDB Chronological Replay] -.->|Historical Ticks| MDF
        MDF -->|Normalized Tick Dataclass| Q[(Bounded queue.Queue\nmaxsize=10,000)]
        MDF -.->|Asynchronous Batch Persist| DB_TICKS[(ticks Table)]
    end

    subgraph Processing & Strategies [Consumer Thread]
        Q --> SE[SignalEngine]
        SE --> MAC[MovingAverageCrossover]
        SE --> RSI[RSIStrategy]
        SE --> BB[MeanReversionStrategy]
        MAC & RSI & BB -->|Evaluates| SIG{Signal Generated?}
        SIG -->|Yes| DB_SIGS[(signals Table)]
    end

    subgraph Execution & Risk [100% Simulated Order Engine]
        SIG -->|Yes| OE[OrderExecutor]
        OE -->|Enforce Risk Limits & Slippage| PORT[Simulated Portfolio State]
        PORT -->|Guarded by threading.Lock| CASH[Simulated Cash & Positions]
        OE -->|Record Simulated Orders| DB_ORDERS[(orders Table)]
    end

    subgraph Live Streaming & UI [FastAPI + WebSockets]
        PORT & DB_SIGS & DB_TICKS --> WS[WebSocket Live Broadcast]
        WS --> UI[Chart.js Terminal Dashboard]
    end

    subgraph AI Intelligence [Google Gemini API]
        DB_SIGS & DB_TICKS --> AI[AITradingAssistant]
        PORT --> AI
        AI -->|Grounded Rationale / Q&A| GEMINI[Google Gemini]
        GEMINI --> UI
    end
```

---

## 🚀 Tech Stack

- **Language:** Python 3.11+ (verified on 3.11 through 3.14)
- **Backend Framework:** FastAPI (Asynchronous lifespan, REST APIs, WebSocket streaming)
- **Concurrency:** `threading.Thread`, `queue.Queue`, `threading.Lock`, `threading.Event`
- **Database & ORM:** PostgreSQL / SQLite via SQLAlchemy 2.0 (Alembic-free automatic startup schema creation)
- **Frontend Dashboard:** Vanilla HTML5, CSS3 (Dark Theme), Modern JavaScript, and Chart.js CDN
- **AI Integration:** Google Gemini API (`google-genai` Python SDK, `gemini-3.8-flash`)
- **Testing:** pytest (57 unit and end-to-end integration tests)
- **Deployment:** Render (`render.yaml`), Railway (`Procfile`), and Docker (`docker-compose.yml`)

---

## 📂 Folder Structure

```
trading-engine/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, WebSocket broadcast, and REST endpoints
│   ├── config.py            # Environment configurations (pydantic-settings, Twelve Data)
│   ├── db.py                # Database connection, session management, SQLite auto-migrations
│   ├── models.py            # SQLAlchemy models (Tick, Signal, Order, Position, PortfolioSnapshot)
│   ├── data/                # Market data providers abstraction layer
│   │   ├── __init__.py
│   │   ├── base.py          # Abstract MarketDataProvider, normalized Tick, validation, telemetry
│   │   ├── twelve_data.py   # Real-time WebSocket provider for Twelve Data with backoff
│   │   ├── simulator.py     # Brownian motion random walk simulator provider
│   │   └── replay.py        # Historical replay provider
│   ├── data_feed.py         # Producer MarketDataFeed wrapping pluggable providers
│   ├── strategies/
│   │   ├── base.py          # Strategy ABC
│   │   ├── moving_average.py# SMA fast/slow crossover
│   │   ├── rsi.py           # Relative Strength Index (oversold/overbought)
│   │   └── mean_reversion.py# Bollinger Bands mean-reversion
│   ├── engine/
│   │   ├── signal_engine.py # Consumer SignalEngine dispatching ticks to strategies
│   │   ├── order_executor.py# OrderExecutor (sizing, slippage, commission, risk rules)
│   │   └── portfolio.py     # Thread-safe Portfolio (threading.Lock, cash, positions, P&L)
│   ├── ws_manager.py        # ConnectionManager for WebSocket live broadcast
│   └── ai_assistant.py      # AITradingAssistant with grounded Google Gemini API queries
├── static/
│   ├── index.html           # Dark-mode live trading terminal UI with Chart.js & telemetry badge
│   └── app.js               # WebSocket client, Chart.js updates, dynamic symbols & telemetry
├── tests/
│   ├── __init__.py
│   ├── test_market_data.py  # Normalized Tick, validate_tick(), queue overflow telemetry
│   ├── test_twelve_data.py  # Mocked Twelve Data WebSocket connection, backoff, message parsing
│   ├── test_simulator.py    # SimulationProvider Brownian random-walk & dynamic subscribe
│   ├── test_replay.py       # HistoricalReplayProvider chronological ordering & speed tests
│   ├── test_market_data_status.py # /api/market-data/symbols & status endpoint tests
│   ├── test_mock_twelve_data_pipeline.py # End-to-end Twelve Data tick to simulated portfolio test
│   ├── test_data_feed.py    # MarketDataFeed queue delivery, thread lifecycle
│   ├── test_strategies.py   # Unit tests for MA crossover, RSI, Bollinger Bands
│   ├── test_portfolio.py    # Cash, positions, P&L, concurrent ThreadPool stress test
│   ├── test_order_executor.py# Position sizing, slippage/commission, risk limit rejection
│   ├── test_signal_engine.py# Synthetic tick processing & order dispatch
│   ├── test_integration.py  # 100-tick end-to-end simulation test
│   └── test_ai_assistant.py # Mocked Google Gemini API tests, prompt grounding verification
├── docker-compose.yml       # Local PostgreSQL 16 container
├── render.yaml              # Render Blueprint for web service + PostgreSQL database
├── Procfile                 # Railway process runner
├── requirements.txt         # Core dependencies
├── .env.example             # Template environment variables
├── .env                     # Local configuration
└── README.md                # Documentation & usage guide
```

---

## ⚡ Quick Start Guide

### 1. Prerequisites
- Python 3.11+ installed.
- (Optional) Docker and Docker Compose for running PostgreSQL locally.

### 2. Environment Setup

Clone or enter the project directory:
```bash
cd trading-engine
```

Create and activate a virtual environment:
```bash
# Windows
python -m venv .venv
.\.venv\Scripts\activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

Configure environment variables:
```bash
cp .env.example .env
```
*(Default `.env` is pre-configured with `sqlite:///./trading.db` for instant local development. For PostgreSQL, set `DATABASE_URL=postgresql://user:password@localhost:5432/trading_db`)*.

### 3. Database Options

#### Option A: Local Zero-Config SQLite (Default)
No setup required. Tables will be created automatically on startup in `trading.db`.

#### Option B: Local PostgreSQL with Docker Compose
```bash
docker compose up -d
```
This launches a PostgreSQL 16 database matching the configuration in `.env.example`.

### 4. Running the Application

Launch the FastAPI application with Uvicorn:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Open your browser and navigate to:
👉 **[http://localhost:8000](http://localhost:8000)**

---

## 🌐 Real-Time Market Data Integration (Twelve Data)

The platform features a modular, pluggable **Market Data Abstraction Layer** conforming to the Open/Closed Principle:

### Supported Market Data Modes (`MARKET_DATA_MODE`):

1. **`live` — Twelve Data WebSocket Streaming**
   - Connects directly to `wss://ws.twelvedata.com/v1/quotes/price?apikey=${TWELVE_DATA_API_KEY}`.
   - Subscribes dynamically to configured equity symbols (`AAPL,MSFT,GOOGL,AMZN,TSLA,NVDA,META`).
   - Normalizes incoming `price` events into internal `Tick` dataclasses with `Decimal` precision.
   - **Bounded Exponential Backoff**: Reconnects on connection drops starting at 1.0s and doubling up to 30.0s max.
   - **Strict Configuration Enforcement**: If `MARKET_DATA_MODE=live` without a valid `TWELVE_DATA_API_KEY`, the application immediately raises a configuration error at startup and **never silently falls back** to simulation.

2. **`simulation` — Synthetic Brownian Random Walk (Default)**
   - Generates realistic geometric Brownian motion ticks with customizable volatility (`TICK_VOLATILITY=0.001`) and interval (`TICK_INTERVAL_SECONDS=1.0`).
   - Requires zero external credentials for safe, self-contained local testing and development.
   - All ticks tagged `source="simulation"`.

3. **`replay` — Chronological Historical Replay**
   - Ingests past market ticks from PostgreSQL or preloaded datasets.
   - Replays ticks chronologically through the exact same producer-consumer queue with adjustable speed multipliers.
   - All ticks tagged `source="historical_replay"`.

> [!CAUTION]
> ### 🔒 Strict Simulation Constraint
> The system consumes real-time market data but **MUST NOT and DOES NOT place real trades**. All orders, risk checks, positions, and executions remain 100% simulated inside our application. No real trading accounts or exchange broker APIs are connected.

---

## 📊 Live Dashboard Features

- **Telemetry & Price Chart:** Live updating Chart.js line chart with interactive ticker selector (`AAPL`, `MSFT`, `GOOGL`, `AMZN`, `TSLA`, `NVDA`, `META`).
- **Data Source Badge & Indicator:** Header badge dynamically shows `LIVE — TWELVE DATA`, `SIMULATION`, or `HISTORICAL REPLAY`, accompanied by a live status dot (`CONNECTED`, `RECONNECTING`, `DISCONNECTED`).
- **Telemetry Details Bar:** Live visibility into Active Provider, Mode, Queue Size (`0 / 10000`), Processed Ticks, and Dropped Ticks.
- **KPI Metrics Cards:** Real-time updates for **Total Equity**, **Cash Balance**, **Unrealized P&L**, and **Realized P&L**.
- **Active Positions Table:** Live table detailing open share counts, average entry prices, current market values, and individual unrealized P&L.
- **Generated Signals:** Real-time stream of strategy triggers with an interactive **"Why?"** button.
- **ChartBot Trading Assistant:** Built-in technical chart and portfolio Q&A assistant to query your stock price trends, indicators (RSI, MA Crossover, Bollinger Bands), cash, open positions, and strategy signal math.

---

## 🤖 Built-In ChartBot Assistant

The `ChartBotAssistant` runs 100% locally with zero external API dependencies or costs:

### Features:
1. **Live Chart & Price Telemetry**: Instant quotes, 30-tick high/low ranges, trend evaluation (📈 Bullish, 📉 Bearish, ⚖️ Neutral), support & resistance levels, and volume.
2. **Strategy & Indicator Explanations**: Instant mathematical explanations of **Moving Average Crossover** (SMA 5 vs 20), **RSI** (14-period, 30/70 thresholds), and **Bollinger Bands** (20-period SMA ± 2 standard deviations).
3. **Portfolio & Capital Status**: Real-time total equity, available cash, liquidity ratio, active holdings, and realized/unrealized P&L.
4. **`explain_signal(signal_id)`**: Mathematical breakdown of why an algorithmic signal fired, citing verified indicator numbers and market data source.

---

## 🧪 Running Automated Tests

Run the complete test suite (62 tests):
```bash
pytest tests/ -v
```

### Test Coverage Summary:
- `tests/test_market_data.py`: Normalized `Tick` dataclass, price/symbol/volume validation, bounded queue overflow protection, and telemetry output.
- `tests/test_twelve_data.py`: Mocked Twelve Data WebSocket connection, subscription handshake, price parsing, heartbeat/error events, and bounded exponential backoff (1s -> 30s).
- `tests/test_simulator.py`: Brownian random-walk synthetic tick generation, thread lifecycle, and dynamic subscription.
- `tests/test_replay.py`: Historical replay chronological ordering, speed multiplier, and dataset completion.
- `tests/test_market_data_status.py`: REST endpoints `/api/market-data/symbols` and `/api/market-data/status` plus `/health` telemetry checks.
- `tests/test_mock_twelve_data_pipeline.py`: Full end-to-end integration test routing mocked Twelve Data ticks into `queue.Queue` -> `SignalEngine` -> `MovingAverageCrossover` -> `OrderExecutor` -> `Portfolio`.
- `tests/test_data_feed.py`: Tick bounds, queue delivery, thread start/stop lifecycle.
- `tests/test_strategies.py`: Synthetic price sequences with known crossover, RSI oversold/overbought, and Bollinger Band boundary breaches.
- `tests/test_portfolio.py`: Cash/position updates, weighted average entry prices, realized/unrealized P&L, and a concurrent stress test using `ThreadPoolExecutor`.
- `tests/test_order_executor.py`: Sizing calculations, 0.05% slippage, $1 flat commission, and risk limit rejection.
- `tests/test_signal_engine.py`: Queue consumption, strategy dispatch, and order executor integration.
- `tests/test_integration.py`: Complete 100-tick end-to-end simulated run across data feed, signal engine, and order executor.
- `tests/test_ai_assistant.py`: Mocked Google Gemini API calls verifying prompt context grounding, source citation, response parsing, and dynamic API key updates.
- `tests/test_api.py`: FastAPI endpoints covering portfolio, trades, signals, strategies, assistant status, dynamic key configuration, and dashboard UI.

---

## 📡 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Service health status, thread liveness, and market data status |
| `GET` | `/` | Serves the live trading terminal dashboard |
| `GET` | `/api/market-data/symbols` | Returns active traded symbol list, count, and mode |
| `GET` | `/api/market-data/status` | Real-time market data feed provider telemetry, queue size, and processed/dropped counts |
| `GET` | `/api/portfolio` | Current portfolio snapshot (equity, cash, positions, P&L) |
| `GET` | `/api/trades` | List of recent order executions |
| `GET` | `/api/signals` | List of recent trading signals |
| `GET` | `/api/strategies` | List of active strategy configurations |
| `GET` | `/api/assistant/status` | Current AI assistant connection status and active model |
| `POST` | `/api/assistant/set-key` | Dynamically update and test Google Gemini API key |
| `POST` | `/api/assistant/ask` | Send a question to Gemini AI assistant |
| `GET` | `/api/assistant/explain/{id}` | Request grounded Gemini explanation for a signal |
| `WS` | `/ws` | Real-time WebSocket connection streaming ticks, signals, equity, and feed telemetry |

---

## 🚀 Deployment

### Deploy to Render

1. Connect your GitHub repository to Render.
2. Render will automatically detect `render.yaml` and provision:
   - A managed PostgreSQL instance (`trading-engine-db`).
   - A web service running `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Set your `GEMINI_API_KEY` in the Render Environment Variables tab.
4. Render monitors the `/health` endpoint for zero-downtime deployments.

### Deploy to Railway

1. Deploy the repository to Railway.
2. Add a PostgreSQL plugin to your Railway project.
3. Railway automatically recognizes the `Procfile`:
   ```Procfile
   web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
   ```
4. Configure `DATABASE_URL` (automatically linked from Railway PostgreSQL) and `GEMINI_API_KEY`.
