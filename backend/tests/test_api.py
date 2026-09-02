import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestHealthEndpoints:
    def test_liveness(self):
        r = client.get("/health/live")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_readiness(self):
        r = client.get("/health/ready")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    def test_market_data_health(self):
        r = client.get("/api/v1/health/market-data")
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] in ("fyers", "upstox", "kotak_neo", "binance")
        assert data["mode"] in ("OFFLINE", "LIVE", "DEMO")


class TestMarketEndpoints:
    def test_get_all_quotes(self):
        r = client.get("/api/v1/markets/quotes")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert "meta" in body
        assert body["error"] is None
        assert len(body["data"]) == 5  # NIFTY, BANKNIFTY, FINNIFTY, SENSEX, VIX

    def test_get_single_quote(self):
        r = client.get("/api/v1/markets/NIFTY/quote")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["symbol"] == "NIFTY 50"
        assert body["meta"]["status"] in ("OFFLINE", "LIVE", "DEMO", "STALE", "CLOSED")

    def test_get_invalid_symbol(self):
        r = client.get("/api/v1/markets/INVALID/quote")
        assert r.status_code == 404

    def test_get_candles(self):
        r = client.get("/api/v1/markets/NIFTY/candles?timeframe=5m")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) > 0
        # Verify candle structure
        candle = body["data"][0]
        assert "timestamp" in candle
        assert "open" in candle
        assert "high" in candle
        assert "low" in candle
        assert "close" in candle
        assert "volume" in candle

    def test_invalid_timeframe(self):
        r = client.get("/api/v1/markets/NIFTY/candles?timeframe=3m")
        assert r.status_code == 422  # Validation error

    def test_market_status(self):
        r = client.get("/api/v1/markets/status")
        assert r.status_code == 200

    def test_market_breadth(self):
        r = client.get("/api/v1/markets/breadth")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["status"] in ("OFFLINE", "LIVE", "DEMO", "STALE", "CLOSED")

    def test_index_cards(self):
        r = client.get("/api/v1/markets/cards")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) == 5

    def test_response_envelope(self):
        """All market responses must use the standard envelope."""
        r = client.get("/api/v1/markets/quotes")
        body = r.json()
        assert "data" in body
        assert "error" in body
        assert "meta" in body
        assert "provider" in body["meta"]
        assert "timestamp" in body["meta"]
        assert "status" in body["meta"]
