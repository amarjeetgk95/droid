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
        """Truth-of-Wall: builds only off a LIVE spot — 503 when the feed is down,
        never a strategy on a hardcoded price."""
        r = client.post("/api/v1/strategy/build-template?template_id=bull_call_spread&symbol=NIFTY")
        body = r.json()
        if r.status_code == 200:
            # Live feed present: strikes key off the real spot.
            spot = body["data"]["spot_price"]
            assert spot > 0
            assert body["data"]["legs"][0]["strike"] == spot
            assert "premium_note" in body["data"]
            assert "payoff_curve" in body["data"]
        else:
            assert r.status_code == 503
            assert "no live" in str(body.get("detail", "")).lower()

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
        """Truth-of-Wall: no fabricated recommendations — honest empty result
        with the limitation stated until real chain analytics are wired in."""
        r = client.get("/api/v1/strategy/scanner?min_pop=20.0")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["scans"] == []
        assert body["data"]["count"] == 0
        assert "not yet wired" in body["data"]["limitation"]
