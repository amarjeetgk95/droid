"""
Direct Provider: OpenAI — §11
Supports chat completions, streaming, and tool execution.
"""
import json
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import structlog

from app.ai.providers.openai_compatible import OpenAICompatibleProvider
from app.ai.streaming import ReasoningExtractor
from app.models.ai import AIChatMessage, AIChatStreamChunk

logger = structlog.get_logger()


class OpenAIProvider(OpenAICompatibleProvider):
    _provider_name = "openai"
    provider_label = "OpenAI"
    api_key_setting = "openai_api_key"
    model_setting = "openai_model"
    base_url_setting = "custom_openai_base_url"
    default_model = "gpt-4o-mini"
    default_base_url = "https://api.openai.com/v1"
    use_structured_outputs = True

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code == 401:
            raise ValueError("OpenAI 401 Unauthorized – API key invalid")
        if resp.status_code == 429:
            raise ValueError("OpenAI 429 Rate Limited")
        if resp.status_code != 200:
            raise ValueError(f"OpenAI {resp.status_code}: {resp.text[:600]}")

    async def get_model_info(self, model_id: str) -> dict:
        models = await self.list_models()
        for m in models:
            if m.get("id") == model_id:
                return m
        return {"id": model_id, "supports_structured_outputs": True}

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
