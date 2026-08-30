from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


class TestAIEndpoints:
    def test_generate_ai_analysis_api(self):
        r = client.post("/api/v1/ai/analyze/NIFTY?provider=mock_ai")
        assert r.status_code == 200
        body = r.json()
        assert "data" in body
        assert body["data"]["symbol"] == "NIFTY"
        assert "market_bias" in body["data"]
        assert "confidence" in body["data"]
        assert "executive_summary" in body["data"]
        assert "options_interpretation" in body["data"]
        assert "futures_flow_analysis" in body["data"]
        assert "recommended_strategy_framework" in body["data"]
        assert "risk_management_notes" in body["data"]

    def test_ai_history_api(self):
        # Generate one to populate history
        client.post("/api/v1/ai/analyze/FINNIFTY?provider=mock_ai")
        r = client.get("/api/v1/ai/history/FINNIFTY")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 1
        assert body["data"][0]["symbol"] == "FINNIFTY"
