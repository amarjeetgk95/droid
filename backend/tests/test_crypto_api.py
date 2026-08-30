import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_get_crypto_tickers(client):
    response = client.get("/api/v1/crypto/tickers")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0
    btc = next((t for t in data["data"] if t["symbol"] == "BTCUSDT"), None)
    assert btc is not None
    assert btc["price"] > 0
    assert "sparkline" in btc


def test_get_crypto_quote(client):
    response = client.get("/api/v1/crypto/BTCUSDT/quote")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert data["data"]["symbol"] == "BTCUSDT"
    assert data["data"]["base_asset"] == "BTC"
    assert data["data"]["price"] > 0


def test_get_crypto_candles(client):
    response = client.get("/api/v1/crypto/BTCUSDT/candles?timeframe=1h&limit=20")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]) > 0
    first = data["data"][0]
    assert "open" in first
    assert "high" in first
    assert "low" in first
    assert "close" in first


def test_get_crypto_order_book(client):
    response = client.get("/api/v1/crypto/BTCUSDT/orderbook?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert len(data["data"]["bids"]) > 0
    assert len(data["data"]["asks"]) > 0
    assert "spread" in data["data"]


def test_get_crypto_derivatives(client):
    response = client.get("/api/v1/crypto/BTCUSDT/derivatives")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert data["data"]["symbol"] == "BTCUSDT"
    assert "funding_rate" in data["data"]
    assert "open_interest_usd" in data["data"]
    assert "long_short_ratio" in data["data"]


def test_get_crypto_market_overview(client):
    response = client.get("/api/v1/crypto/market-overview")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "fear_greed_score" in data["data"]
    assert "btc_dominance_pct" in data["data"]
    assert "top_gainers" in data["data"]
