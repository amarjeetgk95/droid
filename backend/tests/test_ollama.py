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
        # Strict mode: unreachable Ollama should raise ValueError with actionable message, not silent fallback
        offline_provider = OllamaProvider(base_url="http://localhost:65534")
        with pytest.raises(ValueError, match="Ollama not reachable|connectivity check failed"):
            await offline_provider.generate_analysis(
                symbol="NIFTY",
                system_prompt="Analyze market regime",
                user_prompt="Provide forecast",
            )
