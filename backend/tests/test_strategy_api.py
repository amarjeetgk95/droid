from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestStrategyEndpoints:
    def test_get_templates_api(self):
        r = client.get("/api/v1/strategy/templates")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 8

    def test_build_template_api(self):
        r = client.post("/api/v1/strategy/build-template?template_id=bull_call_spread&symbol=NIFTY")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["underlying"] == "NIFTY"
        assert len(body["data"]["legs"]) == 2
        assert "payoff_curve" in body["data"]

    def test_calculate_payoff_custom_api(self):
        payload = {
            "underlying": "NIFTY",
            "spot_price": 25000.0,
            "expiry": "2026-09-03",
            "legs": [
                {
                    "id": "leg1",
                    "option_type": "CE",
                    "side": "BUY",
                    "strike": 25000.0,
                    "quantity": 1,
                    "price": 140.0,
                    "iv": 0.15,
                    "expiry": "2026-09-03",
                    "lot_size": 75,
                }
            ],
        }
        r = client.post("/api/v1/strategy/payoff", json=payload)
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["underlying"] == "NIFTY"
        assert len(body["data"]["payoff_curve"]) > 0

    def test_scanner_api(self):
        r = client.get("/api/v1/strategy/scanner?min_pop=20.0")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) > 0
