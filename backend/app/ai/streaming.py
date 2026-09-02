"""
AI Streaming & Server-Sent Events (SSE) Engine
Provides structured event chunk serialization, reasoning token extraction, and SSE response helpers.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator, Any
from app.models.ai import AIChatStreamChunk


def sse_event(chunk: AIChatStreamChunk) -> str:
    """Format a stream chunk as an SSE data frame."""
    return f"data: {chunk.model_dump_json()}\n\n"


def sse_content_chunk(delta: str, model_used: str | None = None, provider_used: str | None = None) -> str:
    return sse_event(AIChatStreamChunk(
        type="content",
        delta=delta,
        model_used=model_used,
        provider_used=provider_used,
    ))


def sse_reasoning_chunk(reasoning_delta: str, model_used: str | None = None, provider_used: str | None = None) -> str:
    return sse_event(AIChatStreamChunk(
        type="reasoning",
        reasoning_delta=reasoning_delta,
        model_used=model_used,
        provider_used=provider_used,
    ))


def sse_tool_call_chunk(tool_call: dict[str, Any], model_used: str | None = None) -> str:
    return sse_event(AIChatStreamChunk(
        type="tool_call",
        tool_call=tool_call,
        model_used=model_used,
    ))


def sse_tool_result_chunk(tool_result: dict[str, Any]) -> str:
    return sse_event(AIChatStreamChunk(
        type="tool_result",
        tool_result=tool_result,
    ))


def sse_done_chunk(finish_reason: str = "stop", model_used: str | None = None, provider_used: str | None = None) -> str:
    return sse_event(AIChatStreamChunk(
        type="done",
        finish_reason=finish_reason,
        model_used=model_used,
        provider_used=provider_used,
    ))


def sse_error_chunk(error_message: str, provider_used: str | None = None) -> str:
    return sse_event(AIChatStreamChunk(
        type="error",
        delta=error_message,
        provider_used=provider_used,
    ))


class ReasoningExtractor:
    """
    State machine parser to detect and extract <think>...</think> reasoning tags
    from streaming tokens (e.g., DeepSeek R1 models emitting raw tags).
    """

    def __init__(self):
        self.in_think = False
        self.buffer = ""

    def process(self, delta: str) -> list[tuple[str, str]]:
        """
        Takes raw delta string, returns a list of (type, text) tuples where
        type is either 'reasoning' or 'content'.
        """
        if not delta:
            return []

        results: list[tuple[str, str]] = []
        text = self.buffer + delta
        self.buffer = ""

        while text:
            if not self.in_think:
                if "<think>" in text:
                    before, after = text.split("<think>", 1)
                    if before:
                        results.append(("content", before))
                    self.in_think = True
                    text = after
                elif "<" in text and not any(tag in text for tag in ["<think>", "</think>"]):
                    # Potential partial tag at the end of stream
                    idx = text.rfind("<")
                    if len(text) - idx < 10:  # length of '<think>' is 7
                        self.buffer = text[idx:]
                        before = text[:idx]
                        if before:
                            results.append(("content", before))
                        break
                    else:
                        results.append(("content", text))
                        break
                else:
                    results.append(("content", text))
                    break
            else:
                if "</think>" in text:
                    think_content, after = text.split("</think>", 1)
                    if think_content:
                        results.append(("reasoning", think_content))
                    self.in_think = False
                    text = after
                elif "<" in text and "</" in text:
                    idx = text.rfind("<")
                    if len(text) - idx < 10:
                        self.buffer = text[idx:]
                        before = text[:idx]
                        if before:
                            results.append(("reasoning", before))
                        break
                    else:
                        results.append(("reasoning", text))
                        break
                else:
                    results.append(("reasoning", text))
                    break

        return results
