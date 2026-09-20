import pytest
from starlette.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def test_get_market_data_symbols_endpoint(client):
    res = client.get("/api/market-data/symbols")
    assert res.status_code == 200
    data = res.json()
    assert "symbols" in data
    assert "count" in data
    assert "mode" in data
    assert isinstance(data["symbols"], list)
    assert data["count"] == len(data["symbols"])
    assert data["count"] > 0


def test_get_market_data_status_endpoint(client):
    res = client.get("/api/market-data/status")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "market_data" in data

    md = data["market_data"]
    assert "mode" in md
    assert "provider" in md
    assert "connection_status" in md
    assert "symbols" in md
    assert "symbols_list" in md
    assert "queue_size" in md
    assert "max_queue_size" in md
    assert "ticks_processed" in md
    assert "dropped_ticks" in md


def test_health_check_includes_market_data(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "market_data_mode" in data
    assert "market_data_status" in data
    assert data["market_data_status"]["provider"] is not None
