from fastapi.testclient import TestClient
from app.main import app
from app.services.fii_dii_service import fii_dii_service

client = TestClient(app)


class TestFIIDIIService:
    def test_service_calculations(self):
        res = fii_dii_service.get_institutional_overview()
        assert res.fii_long_short_ratio > 0
        assert len(res.breakdown_by_category) == 4
        assert res.institutional_sentiment in [
            "STRONG_BULLISH", "MILD_BULLISH", "NEUTRAL", "MILD_BEARISH", "STRONG_BEARISH"
        ]
        assert len(res.recent_cash_flows) > 0

    def test_api_endpoint(self):
        r = client.get("/api/v1/fii-dii/overview")
        assert r.status_code == 200
        data = r.json()["data"]
        assert "fii_long_short_ratio" in data
        assert "breakdown_by_category" in data
        assert "recent_cash_flows" in data
