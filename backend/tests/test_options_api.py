from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestOptionsEndpoints:
    def test_get_option_chain_api(self):
        r = client.get("/api/v1/options/NIFTY/chain")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert body["data"]["underlying"] == "NIFTY"
        assert len(body["data"]["strikes"]) > 0
        assert "analytics" in body["data"]

    def test_get_options_analytics_api(self):
        r = client.get("/api/v1/options/NIFTY/analytics")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["symbol"] == "NIFTY"
        assert "pcr_oi" in body["data"]
        assert "max_pain_strike" in body["data"]

    def test_get_max_pain_api(self):
        r = client.get("/api/v1/options/NIFTY/max-pain")
        assert r.status_code == 200
        body = r.json()
        assert "max_pain_strike" in body["data"]
        assert "payouts" in body["data"]
