from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestHistoricalEndpoints:
    def test_get_patterns_api(self):
        r = client.get("/api/v1/history/NIFTY/patterns?timeframe=5m")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert isinstance(body["data"], list)

    def test_get_shifts_api(self):
        r = client.get("/api/v1/history/NIFTY/shifts?days=5")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["symbol"] == "NIFTY"
        assert len(body["data"]["shifts"]) == 5

    def test_get_seasonality_api(self):
        r = client.get("/api/v1/history/NIFTY/seasonality")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]["days"]) == 5
        assert "best_day_for_buyers" in body["data"]

    def test_watchlist_api(self):
        # Get Watchlist
        r = client.get("/api/v1/watchlist")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 1

        # Add to Watchlist
        r_add = client.post("/api/v1/watchlist/add?symbol=TCS")
        assert r_add.status_code == 200

        # Remove from Watchlist
        r_del = client.post("/api/v1/watchlist/remove?symbol=TCS")
        assert r_del.status_code == 200
