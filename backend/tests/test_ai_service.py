import pytest
from app.services.ai_service import AIService


class TestAIService:
    @pytest.mark.asyncio
    async def test_generate_market_analysis(self):
        service = AIService()
        insight = await service.generate_market_analysis("NIFTY", "mock_ai")

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
        await service.generate_market_analysis("BANKNIFTY", "mock_ai")
        history = service.get_history("BANKNIFTY")

        assert len(history) >= 1
        assert history[0].symbol == "BANKNIFTY"
        assert history[0].market_bias in ["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"]
