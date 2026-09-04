import json
import httpx
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from app.ai.base import BaseLLMProvider
from app.models.ai import AIInsightResponse, AIChatMessage, AIChatStreamChunk
from app.ai.capability_registry import should_use_structured_outputs, validate_no_unsupported_params
from app.ai.streaming import ReasoningExtractor
import structlog

logger = structlog.get_logger()


class OpenRouterProvider(BaseLLMProvider):
    """OpenRouter Gateway – Claude, DeepSeek, GPT-4o, Llama via unified API with streaming and tool support."""

    def __init__(self, api_key: str | None = None, model: str | None = None):
        from app.core.config import settings as _cfg
        fallback = (getattr(_cfg, "openrouter_api_key", "") or "").strip()
        self.api_key = ((api_key or "").strip() or fallback)
        self.model = (model or getattr(_cfg, "openrouter_default_model", "anthropic/claude-3.7-sonnet") or "anthropic/claude-3.7-sonnet").strip()

    @property
    def provider_name(self) -> str:
        return "openrouter"

    async def list_models(self) -> list[dict[str, Any]]:
        from app.services.openrouter_catalog import get_model_catalog
        catalog = await get_model_catalog()
        return catalog.get("models", [])

    async def get_model_info(self, model_id: str) -> dict[str, Any]:
        from app.services.openrouter_catalog import validate_model_or_raise
        try:
            return await validate_model_or_raise(model_id)
        except Exception:
            from app.ai.capability_registry import get_model_capabilities
            return get_model_capabilities(model_id)

    async def test_connection(self) -> dict[str, Any]:
        if not self.api_key:
            return {"success": False, "provider": "openrouter", "error": "API key missing"}
        if not self.api_key.startswith("sk-or-"):
            return {"success": False, "provider": "openrouter", "error": "API key must start with sk-or-"}
        try:
            from app.services.openrouter_catalog import get_model_catalog
            catalog = await get_model_catalog()
            return {"success": True, "provider": "openrouter", "model": self.model, "free_count": catalog.get("free_count", 0)}
        except Exception as e:
            return {"success": False, "provider": "openrouter", "error": str(e)[:300]}

    async def analyze(self, market_state: dict, task: str) -> dict:
        from app.ai.prompt_builder import build_system_prompt
        system_prompt = build_system_prompt()
        user_prompt = f"Task: {task}\nMarketState: {json.dumps(market_state, default=str)}"
        insight = await self.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, user_prompt)
        return insight.model_dump(mode="json")

    async def generate_analysis(self, symbol: str, system_prompt: str, user_prompt: str) -> AIInsightResponse:
        if not self.api_key:
            raise ValueError("OpenRouter API key is missing. Go to Settings -> AI Engine -> OpenRouter and add your sk-or-v1-... key (from https://openrouter.ai/keys).")
        if not self.api_key.startswith("sk-or-"):
            raise ValueError(f"OpenRouter API key looks invalid (must start with 'sk-or-'). Got: {self.api_key[:12]}...")

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fo-droid.web.app",
            "X-Title": "DROID F&O Analysis",
        }
        use_structured = should_use_structured_outputs(self.model)
        is_signal_prompt = any(k in system_prompt for k in ("decision", "setup_type", "DROID Core Intraday AI", "DROID Scalping AI"))
        prompted_suffix = "\n\nReturn ONLY one valid JSON object. Do not use markdown. Do not include explanations outside the JSON. Do not include code fences."
        response_rule = (
            "\n\nRESPONSE RULE: Output ONLY a valid JSON object with keys: "
            "market_bias, confidence, executive_summary, simple_takeaway, options_interpretation, "
            "futures_flow_analysis, regime_and_levels, recommended_strategy_framework, risk_management_notes, disclaimer. "
            "CRITICAL SCHEMA RULE: Every field except 'confidence' MUST be a flat plain text string (NOT nested objects, NOT dictionaries, NOT lists/arrays). "
            "'confidence' must be a number (0-100). "
            "simple_takeaway is REQUIRED: exactly 2-3 very simple sentences for a beginner. "
            "No markdown code fences, no extra text."
        )
        effective_rule = "" if is_signal_prompt else response_rule
        base_payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt + effective_rule + ("" if use_structured else prompted_suffix)},
                {"role": "user", "content": user_prompt + ("" if use_structured else prompted_suffix)},
            ],
            "temperature": 0.2,
        }
        if use_structured:
            payload_with_json = {**base_payload, "response_format": {"type": "json_object"}}
            payload_with_json = validate_no_unsupported_params(self.model, payload_with_json)
        else:
            payload_with_json = base_payload

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(url, json=payload_with_json, headers=headers)
                if use_structured and resp.status_code == 400 and "structured-outputs" in resp.text:
                    resp = await client.post(url, json=base_payload, headers=headers)
                if resp.status_code == 401:
                    raise ValueError("OpenRouter: 401 Unauthorized – API key invalid or expired.")
                if resp.status_code == 402:
                    raise ValueError("OpenRouter: 402 Payment Required – insufficient credits.")
                if resp.status_code == 429:
                    raise ValueError("OpenRouter: 429 Rate Limited – too many requests. Try again in 30s.")
                if resp.status_code != 200:
                    raise ValueError(f"OpenRouter: {resp.status_code} – {resp.text[:600]}")
                data = resp.json()
                try:
                    content = data["choices"][0]["message"]["content"]
                except (KeyError, IndexError, TypeError):
                    raise ValueError(f"OpenRouter returned unexpected shape: {json.dumps(data)[:400]}")

                if isinstance(content, str):
                    c = content.strip()
                    if c.startswith("```"):
                        parts = c.split("```")
                        if len(parts) >= 2:
                            c = parts[1]
                            if c.lstrip().startswith("json"):
                                c = c.lstrip()[4:]
                            c = c.strip()
                        else:
                            c = c.strip("`").strip()
                    try:
                        parsed = json.loads(c)
                    except json.JSONDecodeError:
                        start_idx = c.find("{")
                        end_idx = c.rfind("}")
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            try:
                                parsed = json.loads(c[start_idx : end_idx + 1])
                            except json.JSONDecodeError as je:
                                raise ValueError(f"OpenRouter returned non-JSON content: {c[:400]} (json error: {je})")
                        else:
                            raise ValueError(f"OpenRouter returned non-JSON content: {c[:400]}")
                else:
                    parsed = content

                if not isinstance(parsed, dict):
                    raise ValueError(f"OpenRouter response root is not a JSON object: {type(parsed)}")

                if is_signal_prompt:
                    parsed.setdefault("provider", "openrouter")
                    parsed.setdefault("model", self.model)
                    return parsed

                return AIInsightResponse(
                    symbol=symbol,
                    timestamp=datetime.now(timezone.utc),
                    market_bias=parsed.get("market_bias", "NEUTRAL"),
                    confidence=parsed.get("confidence", 80.0),
                    executive_summary=parsed.get("executive_summary", ""),
                    simple_takeaway=parsed.get("simple_takeaway", ""),
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

    async def stream_chat(
        self,
        messages: list[AIChatMessage],
        tools: list[dict[str, Any]] | None = None,
        temperature: float = 0.3,
    ) -> AsyncGenerator[AIChatStreamChunk, None]:
        """Stream chat tokens with reasoning and tool call extraction via SSE."""
        if not self.api_key:
            yield AIChatStreamChunk(type="error", delta="OpenRouter API key is missing. Add your sk-or-v1-... key in Settings -> AI Engine.", provider_used="openrouter")
            return

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://fo-droid.web.app",
            "X-Title": "DROID F&O Copilot",
        }

        # Format messages
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
                    if response.status_code == 401:
                        yield AIChatStreamChunk(type="error", delta="OpenRouter 401: Invalid API Key.", provider_used="openrouter")
                        return
                    if response.status_code == 402:
                        yield AIChatStreamChunk(type="error", delta="OpenRouter 402: Insufficient Credits.", provider_used="openrouter")
                        return
                    if response.status_code != 200:
                        err_text = await response.aread()
                        yield AIChatStreamChunk(type="error", delta=f"OpenRouter Error {response.status_code}: {err_text.decode('utf-8', errors='ignore')[:300]}", provider_used="openrouter")
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

                            # 1. Native reasoning delta (OpenRouter DeepSeek-R1 / QwQ)
                            reasoning_delta = delta_obj.get("reasoning") or delta_obj.get("reasoning_content")
                            if reasoning_delta:
                                yield AIChatStreamChunk(
                                    type="reasoning",
                                    reasoning_delta=reasoning_delta,
                                    model_used=self.model,
                                    provider_used="openrouter",
                                )

                            # 2. Tool calls delta
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

                            # 3. Content delta with embedded <think> detection
                            content_delta = delta_obj.get("content", "")
                            if content_delta:
                                parsed_parts = extractor.process(content_delta)
                                for p_type, p_text in parsed_parts:
                                    if p_type == "reasoning":
                                        yield AIChatStreamChunk(
                                            type="reasoning",
                                            reasoning_delta=p_text,
                                            model_used=self.model,
                                            provider_used="openrouter",
                                        )
                                    else:
                                        yield AIChatStreamChunk(
                                            type="content",
                                            delta=p_text,
                                            model_used=self.model,
                                            provider_used="openrouter",
                                        )

                            if finish_reason == "tool_calls" or (finish_reason and tool_calls_accumulator):
                                for _, tc in tool_calls_accumulator.items():
                                    yield AIChatStreamChunk(
                                        type="tool_call",
                                        tool_call=tc,
                                        model_used=self.model,
                                        provider_used="openrouter",
                                    )
                                tool_calls_accumulator.clear()

                            if finish_reason:
                                yield AIChatStreamChunk(
                                    type="done",
                                    finish_reason=finish_reason,
                                    model_used=self.model,
                                    provider_used="openrouter",
                                )

                        except Exception as parse_err:
                            logger.debug("openrouter_stream_parse_warn", error=str(parse_err))

        except Exception as e:
            logger.error("openrouter_stream_failed", error=str(e))
            yield AIChatStreamChunk(type="error", delta=f"OpenRouter Stream Error: {str(e)[:300]}", provider_used="openrouter")
