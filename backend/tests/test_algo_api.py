"""Integration tests for Algo API router (app/api/algo.py).

Verifies that HTTP routes on /api/v1/algo correctly interface with Algo Services
and preserve standard envelope contracts: {data, error, meta}.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.algo.algo_service import reset_algo_caches, DISCLOSURE_VERSION


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def clean_algo():
    reset_algo_caches()
    yield
    reset_algo_caches()


def test_algo_health_endpoint(client: TestClient):
    resp = client.get("/api/v1/algo/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["status"] == "HEALTHY"
    assert "data_freshness" in body["data"]["components"]
    assert body["error"] is None


def test_algo_account_and_mode_endpoints(client: TestClient):
    # GET account
    resp = client.get("/api/v1/algo/account")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "account_id" in data
    assert data["mode"] in ("OFF", "PAPER", "LIVE")

    # POST mode change
    resp2 = client.post("/api/v1/algo/account/mode", json={"mode": "PAPER"})
    assert resp2.status_code == 200
    assert resp2.json()["data"]["mode"] == "PAPER"


def test_algo_consent_endpoints(client: TestClient):
    # GET consent
    resp = client.get("/api/v1/algo/consent")
    assert resp.status_code == 200
    body = resp.json()
    assert "disclosure" in body["data"]

    # POST consent
    resp2 = client.post(
        "/api/v1/algo/consent",
        json={"disclosure_version": DISCLOSURE_VERSION, "acknowledged": True},
    )
    assert resp2.status_code == 200
    assert resp2.json()["data"]["acknowledged"] is True

    # DELETE consent
    resp3 = client.delete("/api/v1/algo/consent")
    assert resp3.status_code == 200
    assert resp3.json()["data"]["revoked"] is True


def test_algo_capital_endpoint(client: TestClient):
    resp = client.get("/api/v1/algo/capital")
    assert resp.status_code == 200
    body = resp.json()
    assert "available" in body["data"]
    assert "config" in body["data"]


def test_algo_sizing_preview_endpoint(client: TestClient):
    resp = client.post(
        "/api/v1/algo/sizing/preview",
        json={
            "entry_price": 100.0,
            "stop_price": 95.0,
            "risk_budget": 500.0,
            "lot_size": 25,
            "available_capital": 25000.0,
        },
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "quantity" in data
    assert data["quantity"] > 0


def test_algo_order_lifecycle_endpoints(client: TestClient, mock_market_open):
    # Create synthetic order
    order_payload = {
        "symbol": "NIFTY24DEC24000CE",
        "side": "BUY",
        "quantity": 50,
        "price": 100.0,
        "order_type": "LIMIT",
        "product": "INTRADAY",
    }
    resp = client.post("/api/v1/algo/orders", json=order_payload)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "client_order_id" in data
    assert data["is_paper"] is True

    # List orders
    resp2 = client.get("/api/v1/algo/orders")
    assert resp2.status_code == 200
    assert isinstance(resp2.json()["data"], list)


def test_algo_slo_and_capabilities(client: TestClient):
    resp1 = client.get("/api/v1/algo/slo-dashboard")
    assert resp1.status_code == 200

    resp2 = client.get("/api/v1/algo/broker-capabilities")
    assert resp2.status_code == 200
    assert "data" in resp2.json()
