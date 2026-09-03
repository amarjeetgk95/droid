import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.models.crypto import ALLOWED_CRYPTO_SYMBOLS


@pytest.fixture
def client():
    return TestClient(app)


def test_get_crypto_tickers_whitelist(client):
    response = client.get("/api/v1/crypto/tickers")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert isinstance(data["data"], list)
    assert len(data["data"]) >= 2

    # Verify that ONLY whitelisted BTC and ETH pairs are returned
    symbols = [t["symbol"] for t in data["data"]]
    for s in symbols:
        assert s in ALLOWED_CRYPTO_SYMBOLS, f"Symbol {s} not in whitelist {ALLOWED_CRYPTO_SYMBOLS}"

    # Ensure no legacy altcoins are present
    disallowed = {"SOLUSDT", "BNBUSDT", "XRPUSDT", "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "LINKUSDT", "NEARUSDT"}
    for bad in disallowed:
        assert bad not in symbols


def test_get_crypto_quote_valid(client):
    response = client.get("/api/v1/crypto/BTCUSDT/quote")
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["symbol"] == "BTCUSDT"
    assert data["data"]["asset"] == "BTC"
    assert data["data"]["price"] > 0

    eth_res = client.get("/api/v1/crypto/ETHUSDT/quote")
    assert eth_res.status_code == 200
    assert eth_res.json()["data"]["symbol"] == "ETHUSDT"
    assert eth_res.json()["data"]["asset"] == "ETH"


def test_get_crypto_quote_rejects_unsupported(client):
    # Any unsupported coin must be strictly rejected with HTTP 400
    response = client.get("/api/v1/crypto/SOLUSDT/quote")
    assert response.status_code == 400
    assert "Unsupported symbol" in response.json()["detail"]

    doge_res = client.get("/api/v1/crypto/DOGE/quote")
    assert doge_res.status_code == 400
    assert "Unsupported symbol" in doge_res.json()["detail"]


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
    ob = data["data"]
    assert len(ob["bids"]) > 0
    assert len(ob["asks"]) > 0
    assert "spread" in ob
    assert "spread_percent" in ob
    assert "sequence_status" in ob
    assert "bid_depth_total" in ob
    assert "ask_depth_total" in ob


def test_get_crypto_derivatives(client):
    response = client.get("/api/v1/crypto/BTCUSDT/derivatives")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    derivs = data["data"]
    assert derivs["symbol"] == "BTCUSDT"
    assert "mark_price" in derivs
    assert "funding_rate" in derivs
    assert "annualized_funding_rate" in derivs
    assert "basis" in derivs
    assert "basis_status" in derivs
    assert "open_interest_usd" in derivs
    assert "long_short_ratio" in derivs


def test_get_crypto_comparison(client):
    response = client.get("/api/v1/crypto/comparison")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    comp = data["data"]
    assert "eth_btc_ratio" in comp
    assert comp["eth_btc_ratio"] > 0
    assert "performance_spread_24h" in comp
    assert "relative_strength" in comp


def test_get_crypto_market_overview(client):
    response = client.get("/api/v1/crypto/market-overview")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    overview = data["data"]
    assert "fear_greed_score" in overview
    assert "btc_dominance_pct" in overview
    assert "eth_dominance_pct" in overview
    assert "eth_btc_ratio" in overview


def test_get_crypto_health(client):
    response = client.get("/api/v1/crypto/health")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    health = data["data"]
    assert "btc" in health
    assert "eth" in health
    assert "websocket" in health
    assert "overall_status" in health
