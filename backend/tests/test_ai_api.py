import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from app.main import app
from app.models.ai import AIInsightResponse

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_openrouter_call():
    def _fake_analysis(symbol, system_prompt, user_prompt):
        return AIInsightResponse(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            market_bias="BULLISH",
            confidence=82.0,
            executive_summary="Institutional accumulation detected with positive delta tilt.",
            options_interpretation="Heavy put writing at ATM strikes with PCR at 1.15.",
            futures_flow_analysis="Long buildup observed with annualized basis premium.",
            regime_and_levels="Trending bullish above key volume POC.",
            recommended_strategy_framework="Bull Call Spread (1:2 risk-reward)",
            risk_management_notes="Strict stop loss below Camarilla S3 support.",
            provider_used="openrouter",
        )

    with patch("app.ai.openrouter.OpenRouterProvider.generate_analysis", new_callable=AsyncMock) as m:
        m.side_effect = _fake_analysis
        yield m


class TestAIEndpoints:
    def test_generate_ai_analysis_api(self):
        r = client.post("/api/v1/ai/analyze/NIFTY?provider=openrouter")
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
        client.post("/api/v1/ai/analyze/FINNIFTY?provider=openrouter")
        r = client.get("/api/v1/ai/history/FINNIFTY")
        assert r.status_code == 200
        body = r.json()
        assert len(body["data"]) >= 1
        assert body["data"][0]["symbol"] == "FINNIFTY"