from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestFuturesEndpoints:
    def test_get_futures_overview_api(self):
        r = client.get("/api/v1/futures/NIFTY/overview")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert body["data"]["underlying"] == "NIFTY"
        assert "term_structure" in body["data"]
        assert "buildup" in body["data"]
        assert "rollover" in body["data"]

    def test_get_term_structure_api(self):
        r = client.get("/api/v1/futures/NIFTY/term-structure")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["underlying"] == "NIFTY"
        assert len(body["data"]["contracts"]) >= 2
        assert "curve_state" in body["data"]

    def test_get_oi_buildup_api(self):
        r = client.get("/api/v1/futures/NIFTY/buildup")
        assert r.status_code == 200
        body = r.json()
        assert "buildup_type" in body["data"]
        assert "interpretation" in body["data"]

    def test_get_rollover_api(self):
        r = client.get("/api/v1/futures/NIFTY/rollover")
        assert r.status_code == 200
        body = r.json()
        assert "rollover_percent" in body["data"]
        assert "rollover_pace" in body["data"]
