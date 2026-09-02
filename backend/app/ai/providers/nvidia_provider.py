"""
Direct Provider: NVIDIA — §11
NVIDIA NIM / AI Foundation Models (OpenAI-compatible)
"""
import json
import httpx
from datetime import datetime, timezone

from app.ai.base import AIProvider
from app.models.ai import AIInsightResponse
import structlog

logger = structlog.get_logger()


class NvidiaProvider(AIProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        from app.core.config import settings as _cfg
        fallback = (getattr(_cfg, "nvidia_api_key", "") or "").strip()
        self.api_key = ((api_key or "").strip() or fallback)
        self.model = (model or getattr(_cfg, "nvidia_model", "meta/llama-3.1-70b-instruct") or "meta/llama-3.1-70b-instruct").strip()
        self.base_url = (base_url or getattr(_cfg, "nvidia_base_url", "") or "https://integrate.api.nvidia.com/v1").rstrip("/") or "https://integrate.api.nvidia.com/v1"

    @property
    def provider_name(self) -> str:
        return "nvidia"

    async def list_models(self) -> list[dict]:
        if not self.api_key:
            raise ValueError("NVIDIA API key missing")
        url = f"{self.base_url}/models"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(url, headers=headers)
            if r.status_code != 200:
                raise ValueError(f"NVIDIA {r.status_code}: {r.text[:300]}")
            return r.json().get("data", [])

    async def get_model_info(self, model_id: str) -> dict:
        try:
            models = await self.list_models()
            for m in models:
                if m.get("id") == model_id:
                    return m
        except Exception:
            pass
        return {"id": model_id}

    async def test_connection(self) -> dict:
        try:
            await self.list_models()
            return {"success": True, "provider": "nvidia", "model": self.model}
        except Exception as e:
            return {"success": False, "provider": "nvidia", "error": str(e)[:300]}

    async def analyze(self, market_state: dict, task: str) -> dict:
        from app.ai.prompt_builder import build_system_prompt
        system_prompt = build_system_prompt()
        user_prompt = f"Task: {task}\nMarketState: {json.dumps(market_state, default=str)}"
        insight = await self.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, user_prompt)
        return insight.model_dump(mode="json")

    async def generate_analysis(self, symbol: str, system_prompt: str, user_prompt: str) -> AIInsightResponse:
        if not self.api_key:
            raise ValueError("NVIDIA API key missing")
        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt + "\n\nReturn ONLY valid JSON object. No markdown."},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        async with httpx.AsyncClient(timeout=60.0) as c:
            r = await c.post(url, json=payload, headers=headers)
            if r.status_code != 200:
                raise ValueError(f"NVIDIA {r.status_code}: {r.text[:500]}")
            data = r.json()
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str):
                c = content.strip()
                if c.startswith("```"):
                    c = c.split("```")[1]
                    if c.lstrip().startswith("json"):
                        c = c.lstrip()[4:]
                    c = c.strip()
                parsed = json.loads(c)
            else:
                parsed = content
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
                provider_used=f"nvidia:{self.model}",
            )
