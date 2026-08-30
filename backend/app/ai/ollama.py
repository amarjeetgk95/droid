import json
import httpx
from datetime import datetime, timezone
from app.ai.base import BaseLLMProvider
from app.ai.mock_ai import MockLLMProvider
from app.models.ai import AIInsightResponse
import structlog

logger = structlog.get_logger()


class OllamaProvider(BaseLLMProvider):
    """Local Ollama AI Provider for offline, zero-cost intelligence (e.g. DeepSeek, Llama3)."""

    def __init__(
        self,
        base_url: str = "https://droid-backend-emeq.onrender.com",
        model: str = "deepseek-r1:latest",
    ):
        self.base_url = base_url
        self.model = model
        self._fallback_provider = MockLLMProvider()

    @property
    def provider_name(self) -> str:
        return "ollama"

    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        """Call local Ollama endpoint or fall back to structured deterministic response."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                prompt_full = f"{system_prompt}\n\nUser Request: {user_prompt}\n\nReturn JSON ONLY matching the required schema."
                payload = {
                    "model": self.model,
                    "prompt": prompt_full,
                    "stream": False,
                    "format": "json",
                }
                res = await client.post(f"{self.base_url}/api/generate", json=payload)
                if res.status_code == 200:
                    data = res.json()
                    response_text = data.get("response", "{}")
                    parsed_json = json.loads(response_text)
                    return AIInsightResponse(
                        symbol=symbol,
                        timestamp=datetime.now(timezone.utc),
                        provider="ollama",
                        **parsed_json,
                    )
        except Exception as e:
            logger.info("ollama_unavailable_falling_back", error=str(e))

        # Seamless deterministic fallback if local Ollama process is not running
        fallback = await self._fallback_provider.generate_analysis(symbol, system_prompt, user_prompt)
        fallback.provider_used = "ollama (local fallback)"
        return fallback
