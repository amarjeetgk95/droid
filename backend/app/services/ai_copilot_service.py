"""
DROID Interactive AI Copilot & Conversational Agent Service
Orchestrates multi-turn market intelligence chats, dynamic tool-calling loops,
and real-time SSE streaming.
"""
from __future__ import annotations

import json
from typing import AsyncGenerator
import structlog

from app.models.ai import AIChatRequest, AIChatMessage, AIChatStreamChunk
from app.ai.streaming import (
    sse_event,
    sse_content_chunk,
    sse_reasoning_chunk,
    sse_tool_call_chunk,
    sse_tool_result_chunk,
    sse_done_chunk,
    sse_error_chunk,
)
from app.ai.tools import AI_TOOLS_SCHEMA, execute_tool
from app.ai.fallback_router import stream_chat_with_fallback
from app.services.market_service import MarketService
from app.services.regime_service import regime_service

logger = structlog.get_logger()


def build_copilot_system_prompt(symbol: str = "NIFTY", context_page: str | None = None) -> str:
    """Build grounded system prompt with page context and quantitative rules."""
    return f"""You are DROID AI Copilot, an elite quantitative analyst and derivatives strategist for the Indian Stock Markets (NSE NIFTY, BANKNIFTY, FINNIFTY, SENSEX, and F&O Equities).

CORE OPERATIONAL PRINCIPLES:
1. Grounding: You have access to real-time quantitative tools (get_market_quote, get_regime_analytics, get_option_chain_summary, get_futures_overview, get_institutional_flow, calculate_options_strategy_payoff). If you need real-time data to answer the user's question accurately, CALL THE RELEVANT TOOL FIRST.
2. Derivatives & Options Discipline: Cross-examine Price Action + 4-Quadrant Futures OI Buildup + Options Chain (PCR, ATM IV, Max Pain, Call/Put Walls) before forming conclusions.
3. Probabilistic & Objective: Never give guaranteed forecasts or calculate exact automated broker execution. Frame insights probabilistically ("structure implies", "options writing concentration indicates support at ₹X").
4. Formats & Clarity: Format explanations using crisp Markdown, bullet points, key level callouts (₹), and concise scenario analysis.

Current Active Symbol: {symbol}
Current UI Context: {context_page or 'Dashboard / Global'}
"""


class AICopilotService:
    """Service managing live interactive Copilot chat turns with tool calling."""

    async def stream_copilot_turn(
        self,
        request: AIChatRequest,
    ) -> AsyncGenerator[str, None]:
        """Stream a complete conversational turn via SSE, resolving tool calls autonomously."""
        messages = list(request.messages)

        # Inject system prompt if not present
        if not messages or messages[0].role != "system":
            sys_prompt = build_copilot_system_prompt(request.symbol, request.context_page)
            messages.insert(0, AIChatMessage(role="system", content=sys_prompt))

        # Max tool call execution loops to prevent infinite loops
        max_tool_loops = 3
        current_loop = 0

        while current_loop < max_tool_loops:
            current_loop += 1
            tool_calls_to_execute: list[dict] = []
            assistant_content_acc = ""
            assistant_reasoning_acc = ""

            req_copy = AIChatRequest(
                messages=messages,
                symbol=request.symbol,
                provider=request.provider,
                model=request.model,
                temperature=request.temperature,
                enable_tools=request.enable_tools,
                allow_paid=request.allow_paid,
                openrouter_api_key=request.openrouter_api_key,
                gemini_api_key=request.gemini_api_key,
                openai_api_key=request.openai_api_key,
                ollama_base_url=request.ollama_base_url,
                ollama_model=request.ollama_model,
            )

            async for chunk in stream_chat_with_fallback(req_copy, tools=AI_TOOLS_SCHEMA if request.enable_tools else None):
                # Emit raw chunk to frontend
                yield sse_event(chunk)

                if chunk.type == "content":
                    assistant_content_acc += chunk.delta
                elif chunk.type == "reasoning":
                    assistant_reasoning_acc += chunk.reasoning_delta
                elif chunk.type == "tool_call" and chunk.tool_call:
                    tool_calls_to_execute.append(chunk.tool_call)

            # If no tool calls were requested, we are done
            if not tool_calls_to_execute:
                break

            # Execute tool calls
            for tc in tool_calls_to_execute:
                fn = tc.get("function", {})
                tool_name = fn.get("name", "")
                tool_args = fn.get("arguments", "{}")
                tool_call_id = tc.get("id", f"call_{tool_name}")

                try:
                    result = await execute_tool(tool_name, tool_args)
                except Exception as ex:
                    result = {"error": str(ex)}

                # Emit tool result chunk to SSE stream
                yield sse_tool_result_chunk({
                    "name": tool_name,
                    "arguments": tool_args,
                    "result": result,
                })

                # Append assistant message with tool calls & tool response to history
                messages.append(AIChatMessage(
                    role="assistant",
                    content=assistant_content_acc,
                    reasoning_content=assistant_reasoning_acc or None,
                    tool_calls=[tc],
                ))
                messages.append(AIChatMessage(
                    role="tool",
                    tool_call_id=tool_call_id,
                    name=tool_name,
                    content=json.dumps(result, default=str),
                ))


ai_copilot_service = AICopilotService()
