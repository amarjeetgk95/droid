"""
Direct Provider: OpenAI — §11

Each provider must have its own adapter.
Do not assume identical API features.
"""
import json
import httpx
from datetime import datetime, timezone

from app.ai.base import AIProvider
from app.models.ai import AIInsightResponse
from app.ai.capability_registry import should_use_structured_outputs
import structlog

logger = structlog.get_logger()


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        self.api_key = (api_key or "").strip()
        self.model = (model or "gpt-4o-mini").strip()
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")

    @property
    def provider_name(self) -> str:
        return "openai"

    async def list_models(self) -> list[dict]:
        if not self.api_key:
            raise ValueError("OpenAI API key missing")
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(url, headers=headers)
            if r.status_code != 200:
                raise ValueError(f"OpenAI list_models {r.status_code}: {r.text[:300]}")
            data = r.json()
            return data.get("data", [])

    async def get_model_info(self, model_id: str) -> dict:
        models = await self.list_models()
        for m in models:
            if m.get("id") == model_id:
                return m
        return {"id": model_id, "supports_structured_outputs": True}

    async def test_connection(self) -> dict:
        try:
            await self.list_models()
            return {"success": True, "provider": "openai", "model": self.model}
        except Exception as e:
            return {"success": False, "provider": "openai", "error": str(e)[:300]}

    async def analyze(self, market_state: dict, task: str) -> dict:
        from app.ai.prompt_builder import build_system_prompt, build_market_context_prompt
        # market_state expected to be dict with regime/futures etc.; build prompts via helper simplified
        system_prompt = build_system_prompt()
        user_prompt = f"Task: {task}\nMarketState: {json.dumps(market_state, default=str)}"
        insight = await self.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, user_prompt)
        return insight.model_dump(mode="json")

    async def generate_analysis(self, symbol: str, system_prompt: str, user_prompt: str) -> AIInsightResponse:
        if not self.api_key:
            raise ValueError("OpenAI API key missing")
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        # Capability-aware: OpenAI supports structured outputs
        if should_use_structured_outputs(self.model):
            base_payload["response_format"] = {"type": "json_object"}
        else:
            base_payload["messages"][0]["content"] += "\n\nReturn ONLY one valid JSON object. Do not use markdown. Do not include explanations outside the JSON. Do not include code fences."

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=base_payload, headers=headers)
            if resp.status_code == 401:
                raise ValueError("OpenAI 401 Unauthorized – API key invalid")
            if resp.status_code == 429:
                raise ValueError("OpenAI 429 Rate Limited")
            if resp.status_code != 200:
                raise ValueError(f"OpenAI {resp.status_code}: {resp.text[:600]}")
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                c = content.strip()
                if c.startswith("```"):
                    parts = c.split("```")
                    if len(parts) >= 2:
                        c = parts[1]
                        if c.lstrip().startswith("json"):
                            c = c.lstrip()[4:]
                    c = c.strip()
                parsed = json.loads(c)
            else:
                parsed = content
            # Normalize bias etc. reuse openrouter normalization minimal
            if "market_bias" in parsed:
                raw_bias = str(parsed.get("market_bias", "NEUTRAL")).upper()
                if raw_bias not in ("BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"):
                    if "BULL" in raw_bias:
                        parsed["market_bias"] = "BULLISH"
                    elif "BEAR" in raw_bias:
                        parsed["market_bias"] = "BEARISH"
                    else:
                        parsed["market_bias"] = "NEUTRAL"
            return AIInsightResponse(
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                market_bias=parsed.get("market_bias", "NEUTRAL"),
                confidence=float(parsed.get("confidence", 75.0)),
                executive_summary=parsed.get("executive_summary", ""),
                options_interpretation=parsed.get("options_interpretation", ""),
                futures_flow_analysis=parsed.get("futures_flow_analysis", ""),
                regime_and_levels=parsed.get("regime_and_levels", ""),
                recommended_strategy_framework=parsed.get("recommended_strategy_framework", ""),
                risk_management_notes=parsed.get("risk_management_notes", ""),
                disclaimer=parsed.get("disclaimer", "Quantitative analysis for research only."),
                provider_used=f"openai:{self.model}",
            )
