import json
import httpx
from datetime import datetime, timezone
from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse, MarketBias
from app.core.config import settings
import structlog

logger = structlog.get_logger()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini AI provider for real-time market analysis."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or getattr(settings, "gemini_api_key", "")

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        """Call Gemini 2.0 / 1.5 Flash API with structured JSON output."""
        if not self.api_key:
            logger.info("gemini_key_missing_falling_back_to_mock")
            from app.ai.mock_ai import MockLLMProvider
            return await MockLLMProvider().generate_analysis(symbol, system_prompt, user_prompt)

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={self.api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]}
            ],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    parsed = json.loads(raw_text)
                    return AIInsightResponse(
                        symbol=symbol,
                        timestamp=datetime.now(timezone.utc),
                        market_bias=parsed.get("market_bias", "NEUTRAL"),
                        confidence=float(parsed.get("confidence", 85.0)),
                        executive_summary=parsed.get("executive_summary", ""),
                        options_interpretation=parsed.get("options_interpretation", ""),
                        futures_flow_analysis=parsed.get("futures_flow_analysis", ""),
                        regime_and_levels=parsed.get("regime_and_levels", ""),
                        recommended_strategy_framework=parsed.get("recommended_strategy_framework", ""),
                        risk_management_notes=parsed.get("risk_management_notes", ""),
                        disclaimer=parsed.get("disclaimer", "Quantitative analysis for research only."),
                        provider_used="gemini",
                    )
                else:
                    logger.warning("gemini_api_error", status=resp.status_code, body=resp.text)
        except Exception as e:
            logger.warning("gemini_call_exception", error=str(e))

        # Fallback to MockLLMProvider on any error or missing key
        from app.ai.mock_ai import MockLLMProvider
        return await MockLLMProvider().generate_analysis(symbol, system_prompt, user_prompt)
