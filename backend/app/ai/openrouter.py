import json
import httpx
from datetime import datetime, timezone
from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse
import structlog

logger = structlog.get_logger()

class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Gateway – Claude, DeepSeek, GPT-4o via unified API. No mock fallback."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = (api_key or "").strip()
        self.model = (model or "anthropic/claude-3.7-sonnet").strip()

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def generate_analysis(self, symbol: str, system_prompt: str, user_prompt: str) -> AIInsightResponse:
        if not self.api_key:
            raise ValueError("OpenRouter API key is missing. Add your sk-or-... key in backend .env OPENROUTER_API_KEY or Terminal Configuration -> AI Engine.")
        if not self.api_key.startswith("sk-or-"):
            raise ValueError(f"OpenRouter API key looks invalid (must start with 'sk-or-'). Got: {self.api_key[:12]}...")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fo-droid.web.app",
            "X-Title": "DROID F&O Analysis",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
        }
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 401:
                    raise ValueError("OpenRouter: 401 Unauthorized – API key invalid or expired. Check AI Engine settings.")
                if resp.status_code == 402:
                    raise ValueError("OpenRouter: 402 Payment Required – insufficient credits.")
                if resp.status_code == 429:
                    raise ValueError("OpenRouter: 429 Rate Limited – too many requests. Try again in 30s.")
                if resp.status_code != 200:
                    raise ValueError(f"OpenRouter: {resp.status_code} – {resp.text[:300]}")
                data = resp.json()
                content = data["choices"][0]["message"]["content"]
                # content may be JSON string
                if isinstance(content, str):
                    parsed = json.loads(content)
                else:
                    parsed = content
                return AIInsightResponse(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    market_bias=parsed.get("market_bias", "NEUTRAL"),
                    confidence=float(parsed.get("confidence", 80.0)),
                    executive_summary=parsed.get("executive_summary", ""),
                    options_interpretation=parsed.get("options_interpretation", ""),
                    futures_flow_analysis=parsed.get("futures_flow_analysis", ""),
                    regime_and_levels=parsed.get("regime_and_levels", ""),
                    recommended_strategy_framework=parsed.get("recommended_strategy_framework", ""),
                    risk_management_notes=parsed.get("risk_management_notes", ""),
                    disclaimer=parsed.get("disclaimer", "Quantitative analysis for research only."),
                    provider_used=f"openrouter:{self.model}",
                )
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"OpenRouter request failed: {str(e)[:300]}")
