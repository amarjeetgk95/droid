from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestAlertsEndpoints:
    def test_list_alerts_api(self):
        r = client.get("/api/v1/alerts")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 3

    def test_create_and_toggle_alert_api(self):
        payload = {
            "name": "NIFTY Fall Alert",
            "symbol": "NIFTY",
            "alert_type": "PRICE_LEVEL",
            "condition": "LESS_THAN",
            "threshold": 24000.0,
            "channel": "IN_APP",
        }
        r = client.post("/api/v1/alerts", json=payload)
        assert r.status_code == 200
        alert_id = r.json()["data"]["id"]

        # Toggle
        r_tog = client.post(f"/api/v1/alerts/{alert_id}/toggle")
        assert r_tog.status_code == 200
        assert r_tog.json()["data"]["is_active"] is False

        # Delete
        r_del = client.delete(f"/api/v1/alerts/{alert_id}")
        assert r_del.status_code == 200

    def test_evaluate_and_history_api(self):
        r_eval = client.post("/api/v1/alerts/evaluate")
        assert r_eval.status_code == 200

        r_hist = client.get("/api/v1/alerts/history")
        assert r_hist.status_code == 200
        assert isinstance(r_hist.json()["data"], list)

    def test_telemetry_api(self):
        r = client.get("/api/v1/alerts/telemetry")
        assert r.status_code == 200
        body = r.json()
        assert body["data"]["status"] == "HEALTHY"
        assert body["data"]["memory_usage_mb"] > 0
