from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestRegimeEndpoints:
    def test_get_regime_overview_api(self):
        r = client.get("/api/v1/regime/NIFTY/overview")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert body["data"]["symbol"] == "NIFTY"
        assert "regime_state" in body["data"]
        assert "confidence_score" in body["data"]
        assert "indicators" in body["data"]
        assert "key_levels" in body["data"]
        assert "vix_regime" in body["data"]

    def test_get_key_levels_api(self):
        r = client.get("/api/v1/regime/NIFTY/pivots")
        assert r.status_code == 200
        body = r.json()
        assert "classic_pivots" in body["data"]
        assert "poc" in body["data"]
        assert "nearest_resistance" in body["data"]

    def test_get_technical_indicators_api(self):
        r = client.get("/api/v1/regime/NIFTY/indicators")
        assert r.status_code == 200
        body = r.json()
        assert "rsi_14" in body["data"]
        assert "adx_14" in body["data"]
        assert "bollinger_bandwidth" in body["data"]

    def test_get_vix_status_api(self):
        r = client.get("/api/v1/regime/vix-status")
        assert r.status_code == 200
        body = r.json()
        assert "regime_category" in body["data"]
        assert "recommended_option_strategy" in body["data"]
