import pytest
from app.ai.ollama import OllamaProvider
from app.ai.registry import get_llm_provider


class TestOllamaProvider:
    def test_registry_registration(self):
        provider = get_llm_provider("ollama")
        assert provider is not None
        assert provider.provider_name == "ollama"

    @pytest.mark.asyncio
    async def test_fallback_when_server_offline(self):
        # Point to an unreachable port to verify resilient fallback
        offline_provider = OllamaProvider(base_url="http://localhost:65534")
        analysis = await offline_provider.generate_analysis(
            symbol="NIFTY",
            system_prompt="Analyze market regime",
            user_prompt="Provide forecast",
        )
        assert analysis.symbol == "NIFTY"
        assert analysis.market_bias in ["BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"]
        assert "fallback" in analysis.provider_used
