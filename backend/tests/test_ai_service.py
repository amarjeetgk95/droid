import pytest
from unittest.mock import patch, AsyncMock
from datetime import datetime, timezone
from app.services.ai_service import AIService
from app.models.ai import AIInsightResponse


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


class TestAIService:
    @pytest.mark.asyncio
    async def test_generate_market_analysis(self):
        service = AIService()
        insight = await service.generate_market_analysis("NIFTY", "openrouter")

        assert insight.symbol == "NIFTY"
        assert insight.market_bias in ["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"]
        assert 0 <= insight.confidence <= 100
        assert len(insight.executive_summary) > 0
        assert len(insight.options_interpretation) > 0
        assert len(insight.futures_flow_analysis) > 0
        assert len(insight.regime_and_levels) > 0
        assert len(insight.recommended_strategy_framework) > 0
        assert len(insight.risk_management_notes) > 0
        assert "strictly for quantitative research" in insight.disclaimer

    @pytest.mark.asyncio
    async def test_history_caching(self):
        service = AIService()
        await service.generate_market_analysis("BANKNIFTY", "openrouter")
        history = service.get_history("BANKNIFTY")

        assert len(history) >= 1
        assert history[0].symbol == "BANKNIFTY"
        assert history[0].market_bias in ["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"]