import json
import httpx
from datetime import datetime, timezone
from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse, MarketBias
from app.core.config import settings
import structlog

logger = structlog.get_logger()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini – strict, no mock fallback. Fails fast with clear errors."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        # Keys are injected per-request from frontend settings; fallback to server env only if explicitly set
        self.api_key = (api_key or "").strip() or getattr(settings, "gemini_api_key", "") or ""
        self.api_key = self.api_key.strip()
        self.model = (model or "gemini-2.0-flash").strip()

    @property
    def provider_name(self) -> str:
        return "gemini"

    async def list_models(self) -> list[dict]:
        if not self.api_key:
            raise ValueError("Gemini API key missing")
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={self.api_key}"
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(url)
            if r.status_code != 200:
                raise ValueError(f"Gemini list_models {r.status_code}: {r.text[:300]}")
            return r.json().get("models", [])

    async def get_model_info(self, model_id: str) -> dict:
        if not self.api_key:
            raise ValueError("Gemini API key missing")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}?key={self.api_key}"
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url)
            if r.status_code != 200:
                return {"name": model_id, "id": model_id}
            return r.json()

    async def test_connection(self) -> dict:
        try:
            models = await self.list_models()
            return {"success": True, "provider": "gemini", "model": self.model, "model_count": len(models)}
        except Exception as e:
            return {"success": False, "provider": "gemini", "error": str(e)[:300]}

    async def analyze(self, market_state: dict, task: str) -> dict:
        from app.ai.prompt_builder import build_system_prompt
        system_prompt = build_system_prompt()
        import json as _j
        user_prompt = f"Task: {task}\nMarketState: {_j.dumps(market_state, default=str)}"
        insight = await self.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, user_prompt)
        return insight.model_dump(mode="json")

    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        if not self.api_key:
            raise ValueError("Gemini API key missing. Add your AIza... key in Terminal Configuration -> AI Engine -> Google Gemini.")
        if not self.api_key.startswith("AIza"):
            raise ValueError(f"Gemini API key looks invalid (must start with 'AIza'). Got: {self.api_key[:12]}...")
        if not self.model:
            raise ValueError("Gemini model not selected.")

        # Map friendly names to API model IDs if needed
        model_id = self.model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:generateContent?key={self.api_key}"
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
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    try:
                        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
                    except (KeyError, IndexError) as e:
                        raise ValueError(f"Gemini returned unexpected shape: {json.dumps(data)[:400]}")
                    parsed = json.loads(raw_text)
                    # Validate required fields
                    if "market_bias" not in parsed or "executive_summary" not in parsed:
                        raise ValueError(f"Gemini JSON missing required fields. Got keys: {list(parsed.keys())}. Raw: {raw_text[:300]}")
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
                        provider_used=f"gemini:{model_id}",
                    )
                elif resp.status_code == 400:
                    raise ValueError(f"Gemini 400 – bad request (check model name '{model_id}'): {resp.text[:400]}")
                elif resp.status_code == 401:
                    raise ValueError("Gemini 401 – invalid API key.")
                elif resp.status_code == 403:
                    raise ValueError("Gemini 403 – API not enabled or quota exceeded. Enable Generative Language API in Google Cloud.")
                elif resp.status_code == 429:
                    raise ValueError("Gemini 429 – rate limited / quota exhausted. Try again in 30s.")
                else:
                    raise ValueError(f"Gemini {resp.status_code}: {resp.text[:400]}")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Gemini request failed: {str(e)[:400]}")
