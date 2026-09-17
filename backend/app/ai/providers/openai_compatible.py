"""
Shared OpenAI-compatible chat-completions provider — §11

OpenAI, Novita, NVIDIA NIM and any custom OpenAI-compatible endpoint speak the
same `/chat/completions` dialect. They differed only in base_url, config keys,
prompted-JSON suffix grammar and a few HTTP error messages, so all shared
behavior (HTTP call, robust JSON extraction, market_bias normalization and
AIInsightResponse construction) lives here once.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from app.ai.base import AIProvider
from app.ai.capability_registry import should_use_structured_outputs
from app.ai.provider_utils import (
    analyze_market_state,
    extract_json_object,
    normalize_market_bias,
)
from app.models.ai import AIInsightResponse


class OpenAICompatibleProvider(AIProvider):
    """Base for providers exposing the OpenAI chat-completions API."""

    # --- provider-specific bits (overridden by subclasses) ---
    _provider_name: str = "openai_compatible"
    provider_label: str = "OpenAI-compatible"
    api_key_setting: str = ""
    model_setting: str = ""
    base_url_setting: str = ""
    default_model: str = ""
    default_base_url: str = ""
    require_api_key: bool = True
    require_base_url: bool = False
    use_structured_outputs: bool = False
    json_prompt_suffix: str = "\n\nReturn ONLY one valid JSON object. Do not use markdown."

    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        # Per-request values are primary; config (env/Settings) is fallback.
        from app.core.config import settings as _cfg

        fallback_key = (getattr(_cfg, self.api_key_setting, "") or "").strip() if self.api_key_setting else ""
        self.api_key = (api_key or "").strip() or fallback_key

        fallback_model = getattr(_cfg, self.model_setting, "") if self.model_setting else ""
        self.model = (model or fallback_model or self.default_model).strip()

        fallback_url = (getattr(_cfg, self.base_url_setting, "") or "").strip() if self.base_url_setting else ""
        effective_base = (base_url or fallback_url or self.default_base_url).strip()
        if not effective_base and self.require_base_url:
            raise ValueError(
                "Custom OpenAI-compatible requires base_url – configure CUSTOM_OPENAI_BASE_URL or pass base_url per-request"
            )
        self.base_url = effective_base.rstrip("/") or self.default_base_url

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code != 200:
            raise ValueError(f"{self.provider_label} {resp.status_code}: {resp.text[:500]}")

    async def list_models(self) -> list[dict]:
        if self.require_api_key and not self.api_key:
            raise ValueError(f"{self.provider_label} API key missing")
        url = f"{self.base_url}/models"
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(url, headers=self._auth_headers())
            if r.status_code != 200:
                raise ValueError(f"{self.provider_label} list_models {r.status_code}: {r.text[:300]}")
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
            return {"success": True, "provider": self._provider_name, "model": self.model}
        except Exception as e:
            return {"success": False, "provider": self._provider_name, "error": str(e)[:300]}

    async def analyze(self, market_state: dict, task: str) -> dict:
        return await analyze_market_state(self, market_state, task)

    async def generate_analysis(self, symbol: str, system_prompt: str, user_prompt: str) -> AIInsightResponse:
        if self.require_api_key and not self.api_key:
            raise ValueError(f"{self.provider_label} API key missing")
        url = f"{self.base_url}/chat/completions"
        headers = {**self._auth_headers(), "Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
        }
        if self.use_structured_outputs and should_use_structured_outputs(self.model):
            payload["response_format"] = {"type": "json_object"}
        else:
            payload["messages"][0]["content"] += self.json_prompt_suffix

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            self._raise_for_status(resp)
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = extract_json_object(content, self.provider_label)

            if not isinstance(parsed, dict):
                raise ValueError(f"{self.provider_label} response root is not a JSON object: {type(parsed)}")

            return self._build_insight(symbol, parsed)

    def _build_insight(self, symbol: str, parsed: dict) -> AIInsightResponse:
        return AIInsightResponse(
            symbol=symbol,
            timestamp=datetime.now(timezone.utc),
            market_bias=normalize_market_bias(parsed.get("market_bias", "NEUTRAL")),
            confidence=parsed.get("confidence", 75.0),
            executive_summary=parsed.get("executive_summary", ""),
            simple_takeaway=parsed.get("simple_takeaway", ""),
            options_interpretation=parsed.get("options_interpretation", ""),
            futures_flow_analysis=parsed.get("futures_flow_analysis", ""),
            regime_and_levels=parsed.get("regime_and_levels", ""),
            recommended_strategy_framework=parsed.get("recommended_strategy_framework", ""),
            risk_management_notes=parsed.get("risk_management_notes", ""),
            disclaimer=parsed.get("disclaimer", "Quantitative analysis for research only."),
            provider_used=f"{self._provider_name}:{self.model}",
        )
