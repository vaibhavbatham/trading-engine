import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import init_db


@pytest.fixture(scope="module", autouse=True)
def setup_api_test():
    init_db()


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "data_feed_alive" in data
    assert "signal_engine_alive" in data


def test_get_portfolio_endpoint(client):
    response = client.get("/api/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert "total_equity" in data
    assert "cash_balance" in data
    assert "positions" in data


def test_get_trades_endpoint(client):
    response = client.get("/api/trades")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_signals_endpoint(client):
    response = client.get("/api/signals")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_get_strategies_endpoint(client):
    response = client.get("/api/strategies")
    assert response.status_code == 200
    data = response.json()
    assert "active_strategies_count" in data
    assert data["active_strategies_count"] > 0
    assert len(data["strategies"]) > 0


def test_assistant_ask_endpoint(client):
    response = client.post("/api/assistant/ask", json={"question": "What is my current cash?"})
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert len(data["answer"]) > 0


def test_assistant_ask_empty_question(client):
    response = client.post("/api/assistant/ask", json={"question": "   "})
    assert response.status_code == 400


def test_assistant_explain_endpoint_not_found(client):
    response = client.get("/api/assistant/explain/999999")
    assert response.status_code == 200
    data = response.json()
    assert "not found" in data["explanation"].lower()


def test_serve_dashboard(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "QUANTUM ENGINE" in response.text
    assert "marketChart" in response.text


def test_assistant_status_endpoint(client):
    response = client.get("/api/assistant/status")
    assert response.status_code == 200
    data = response.json()
    assert data["bot_name"] == "ChartBot"
    assert data["active"] is True
    assert "ChartBot" in data["model"]


def test_assistant_set_key_endpoint(client):
    response = client.post("/api/assistant/set-key", json={"api_key": "some_test_key"})
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["active"] is True
    assert "locally" in data["message"] or "ChartBot" in data["message"]


def test_set_market_data_config_endpoint(client):
    # Switch to live mode with Twelve Data key and custom symbols
    resp = client.post("/api/market-data/set-config", json={
        "mode": "live",
        "api_key": "td_valid_test_key_999",
        "symbols": "AAPL,MSFT,TSLA",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["mode"] == "live"
    assert "AAPL" in data["symbols"]
    assert "TSLA" in data["symbols"]

    # Switch back to simulation mode
    resp_sim = client.post("/api/market-data/set-config", json={
        "mode": "simulation",
    })
    assert resp_sim.status_code == 200
    data_sim = resp_sim.json()
    assert data_sim["success"] is True
    assert data_sim["mode"] == "simulation"

    # Invalid switch: live mode without API key should fail
    resp_fail = client.post("/api/market-data/set-config", json={
        "mode": "live",
        "api_key": "",
    })
    assert resp_fail.status_code == 400

