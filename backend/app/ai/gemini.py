import json
import httpx
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse, AIChatMessage, AIChatStreamChunk
from app.ai.streaming import ReasoningExtractor
from app.core.config import settings
import structlog

logger = structlog.get_logger()


class GeminiProvider(BaseLLMProvider):
    """Google Gemini – strict, no mock fallback with streaming support."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
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
        user_prompt = f"Task: {task}\nMarketState: {json.dumps(market_state, default=str)}"
        insight = await self.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, user_prompt)
        return insight.model_dump(mode="json")

    async def generate_analysis(
        self,
        symbol: str,
        system_prompt: str,
        user_prompt: str,
    ) -> AIInsightResponse:
        if not self.api_key:
            raise ValueError("Gemini API key missing. Add your AIza... key in Settings -> AI Engine -> Google Gemini.")
        if not self.api_key.startswith("AIza"):
            raise ValueError(f"Gemini API key looks invalid (must start with 'AIza'). Got: {self.api_key[:12]}...")
        if not self.model:
            raise ValueError("Gemini model not selected.")

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
                    except (KeyError, IndexError):
                        raise ValueError(f"Gemini returned unexpected shape: {json.dumps(data)[:400]}")
                    parsed = json.loads(raw_text)
                    if "market_bias" not in parsed or "executive_summary" not in parsed:
                        raise ValueError(f"Gemini JSON missing required fields. Got keys: {list(parsed.keys())}.")
                    return AIInsightResponse(
                        symbol=symbol,
                        timestamp=datetime.now(timezone.utc),
                        market_bias=parsed.get("market_bias", "NEUTRAL"),
                        confidence=float(parsed.get("confidence", 80.0)),
                        executive_summary=parsed.get("executive_summary", ""),
                        simple_takeaway=parsed.get("simple_takeaway", ""),
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
                    raise ValueError("Gemini 403 – API not enabled or quota exceeded.")
                elif resp.status_code == 429:
                    raise ValueError("Gemini 429 – rate limited / quota exhausted.")
                else:
                    raise ValueError(f"Gemini {resp.status_code}: {resp.text[:400]}")
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Gemini request failed: {str(e)[:400]}")

    async def stream_chat(
        self,
        messages: list[AIChatMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[AIChatStreamChunk, None]:
        """Stream conversational chat responses from Gemini via SSE."""
        if not self.api_key:
            yield AIChatStreamChunk(type="error", delta="Gemini API key missing.", provider_used="gemini")
            return

        model_id = self.model
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_id}:streamGenerateContent?alt=sse&key={self.api_key}"

        # Convert AIChatMessages to Gemini contents
        contents = []
        system_instruction_text = ""

        for m in messages:
            if m.role == "system":
                system_instruction_text += f"{m.content}\n"
            else:
                gemini_role = "user" if m.role in ("user", "tool") else "model"
                contents.append({
                    "role": gemini_role,
                    "parts": [{"text": m.content}],
                })

        if not contents:
            contents = [{"role": "user", "parts": [{"text": "Hello"}]}]

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if system_instruction_text:
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction_text.strip()}],
            }

        extractor = ReasoningExtractor()

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        yield AIChatStreamChunk(type="error", delta=f"Gemini Stream Error {response.status_code}: {err_text.decode('utf-8', errors='ignore')[:300]}", provider_used="gemini")
                        return

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        try:
                            chunk_json = json.loads(data_str)
                            candidates = chunk_json.get("candidates", [])
                            if not candidates:
                                continue
                            parts = candidates[0].get("content", {}).get("parts", [])
                            for p in parts:
                                text_part = p.get("text", "")
                                if text_part:
                                    parsed_parts = extractor.process(text_part)
                                    for p_type, p_text in parsed_parts:
                                        if p_type == "reasoning":
                                            yield AIChatStreamChunk(
                                                type="reasoning",
                                                reasoning_delta=p_text,
                                                model_used=model_id,
                                                provider_used="gemini",
                                            )
                                        else:
                                            yield AIChatStreamChunk(
                                                type="content",
                                                delta=p_text,
                                                model_used=model_id,
                                                provider_used="gemini",
                                            )
                        except Exception as parse_err:
                            logger.debug("gemini_stream_parse_warn", error=str(parse_err))

                    yield AIChatStreamChunk(type="done", finish_reason="stop", model_used=model_id, provider_used="gemini")

        except Exception as e:
            logger.error("gemini_stream_failed", error=str(e))
            yield AIChatStreamChunk(type="error", delta=f"Gemini Stream Failed: {str(e)[:300]}", provider_used="gemini")
