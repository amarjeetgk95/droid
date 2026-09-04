"""
Direct Provider: OpenAI — §11
Supports chat completions, streaming, and tool execution.
"""
import json
import httpx
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from app.ai.base import AIProvider
from app.models.ai import AIInsightResponse, AIChatMessage, AIChatStreamChunk
from app.ai.capability_registry import should_use_structured_outputs
from app.ai.streaming import ReasoningExtractor
import structlog

logger = structlog.get_logger()


class OpenAIProvider(AIProvider):
    def __init__(self, api_key: str | None = None, model: str | None = None, base_url: str | None = None):
        # Per-request key fallback to config (env) — Settings UI is primary
        from app.core.config import settings as _cfg
        fallback = (getattr(_cfg, "openai_api_key", "") or "").strip()
        self.api_key = ((api_key or "").strip() or fallback)
        self.model = (model or getattr(_cfg, "openai_model", "gpt-4o-mini") or "gpt-4o-mini").strip()
        self.base_url = (base_url or getattr(_cfg, "custom_openai_base_url", "") or "https://api.openai.com/v1").rstrip("/") or "https://api.openai.com/v1"

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
        from app.ai.prompt_builder import build_system_prompt
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
        if should_use_structured_outputs(self.model):
            base_payload["response_format"] = {"type": "json_object"}
        else:
            base_payload["messages"][0]["content"] += "\n\nReturn ONLY one valid JSON object. Do not use markdown."

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
                simple_takeaway=parsed.get("simple_takeaway", ""),
                options_interpretation=parsed.get("options_interpretation", ""),
                futures_flow_analysis=parsed.get("futures_flow_analysis", ""),
                regime_and_levels=parsed.get("regime_and_levels", ""),
                recommended_strategy_framework=parsed.get("recommended_strategy_framework", ""),
                risk_management_notes=parsed.get("risk_management_notes", ""),
                disclaimer=parsed.get("disclaimer", "Quantitative analysis for research only."),
                provider_used=f"openai:{self.model}",
            )

    async def stream_chat(
        self,
        messages: list[AIChatMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[AIChatStreamChunk, None]:
        """Stream OpenAI chat tokens, tool calls and reasoning deltas via SSE."""
        if not self.api_key:
            yield AIChatStreamChunk(type="error", delta="OpenAI API key missing.", provider_used="openai")
            return

        url = f"{self.base_url}/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        formatted_messages = []
        for m in messages:
            msg_dict: dict[str, Any] = {"role": m.role, "content": m.content}
            if m.tool_calls:
                msg_dict["tool_calls"] = m.tool_calls
            if m.tool_call_id:
                msg_dict["tool_call_id"] = m.tool_call_id
            if m.name:
                msg_dict["name"] = m.name
            formatted_messages.append(msg_dict)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": formatted_messages,
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            payload["tools"] = tools

        extractor = ReasoningExtractor()
        tool_calls_accumulator: dict[int, dict[str, Any]] = {}

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                async with client.stream("POST", url, json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        yield AIChatStreamChunk(type="error", delta=f"OpenAI Stream Error {response.status_code}: {err_text.decode('utf-8', errors='ignore')[:300]}", provider_used="openai")
                        return

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            break

                        try:
                            chunk_json = json.loads(data_str)
                            choice = chunk_json["choices"][0]
                            delta_obj = choice.get("delta", {})
                            finish_reason = choice.get("finish_reason")

                            # Tool calls delta
                            if "tool_calls" in delta_obj and delta_obj["tool_calls"]:
                                for tc in delta_obj["tool_calls"]:
                                    idx = tc.get("index", 0)
                                    if idx not in tool_calls_accumulator:
                                        tool_calls_accumulator[idx] = {
                                            "id": tc.get("id", ""),
                                            "type": "function",
                                            "function": {"name": "", "arguments": ""},
                                        }
                                    if tc.get("id"):
                                        tool_calls_accumulator[idx]["id"] = tc["id"]
                                    fn = tc.get("function", {})
                                    if fn.get("name"):
                                        tool_calls_accumulator[idx]["function"]["name"] += fn["name"]
                                    if fn.get("arguments"):
                                        tool_calls_accumulator[idx]["function"]["arguments"] += fn["arguments"]

                            # Content delta
                            content_delta = delta_obj.get("content", "")
                            if content_delta:
                                parsed_parts = extractor.process(content_delta)
                                for p_type, p_text in parsed_parts:
                                    if p_type == "reasoning":
                                        yield AIChatStreamChunk(type="reasoning", reasoning_delta=p_text, model_used=self.model, provider_used="openai")
                                    else:
                                        yield AIChatStreamChunk(type="content", delta=p_text, model_used=self.model, provider_used="openai")

                            if finish_reason == "tool_calls" or (finish_reason and tool_calls_accumulator):
                                for _, tc in tool_calls_accumulator.items():
                                    yield AIChatStreamChunk(type="tool_call", tool_call=tc, model_used=self.model, provider_used="openai")
                                tool_calls_accumulator.clear()

                            if finish_reason:
                                yield AIChatStreamChunk(type="done", finish_reason=finish_reason, model_used=self.model, provider_used="openai")

                        except Exception as parse_err:
                            logger.debug("openai_stream_parse_warn", error=str(parse_err))

        except Exception as e:
            logger.error("openai_stream_failed", error=str(e))
            yield AIChatStreamChunk(type="error", delta=f"OpenAI Stream Error: {str(e)[:300]}", provider_used="openai")
