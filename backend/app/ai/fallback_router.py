"""
Multi-Provider Fallback Cascade & Resiliency Router
Enables seamless automatic failover across OpenRouter, Gemini, OpenAI, and Ollama.
"""
from __future__ import annotations

import structlog
from typing import AsyncGenerator, Any
from app.models.ai import AIChatRequest, AIChatStreamChunk
from app.ai.registry import create_provider_for_test
from app.ai.base import BaseLLMProvider
from app.core.config import settings

logger = structlog.get_logger()


def resolve_provider_instance(
    provider_name: str,
    model: str | None = None,
    openrouter_api_key: str | None = None,
    gemini_api_key: str | None = None,
    openai_api_key: str | None = None,
    ollama_base_url: str | None = None,
    ollama_model: str | None = None,
) -> BaseLLMProvider:
    """Create a configured provider instance with client-provided keys or environment fallback."""
    p_name = (provider_name or "openrouter").lower()
    return create_provider_for_test(
        p_name,
        model=model,
        openRouterApiKey=openrouter_api_key,
        openRouterModel=model,
        geminiApiKey=gemini_api_key,
        geminiModel=model,
        apiKey=openai_api_key,
        ollamaBaseUrl=ollama_base_url,
        ollamaModel=ollama_model,
    )


async def stream_chat_with_fallback(
    request: AIChatRequest,
    tools: list[dict[str, Any]] | None = None,
) -> AsyncGenerator[AIChatStreamChunk, None]:
    """
    Executes streaming chat against the primary requested provider.
    If the primary provider fails before streaming content (e.g. 429/500/timeout),
    it automatically attempts the secondary fallback provider.
    """
    providers_to_try: list[tuple[str, str | None]] = []

    primary_prov = (request.provider or "openrouter").lower()
    primary_model = request.model
    providers_to_try.append((primary_prov, primary_model))

    # Add secondary fallbacks
    if primary_prov == "openrouter":
        if request.gemini_api_key or getattr(settings, "gemini_api_key", ""):
            providers_to_try.append(("gemini", "gemini-2.0-flash"))
        if request.openai_api_key or getattr(settings, "openai_api_key", ""):
            providers_to_try.append(("openai", "gpt-4o-mini"))
    elif primary_prov == "gemini":
        if request.openrouter_api_key or getattr(settings, "openrouter_api_key", ""):
            providers_to_try.append(("openrouter", "auto"))
        if request.openai_api_key:
            providers_to_try.append(("openai", "gpt-4o-mini"))

    last_error: str | None = None

    for idx, (prov_name, model_name) in enumerate(providers_to_try):
        try:
            logger.info("attempting_ai_provider_stream", provider=prov_name, model=model_name, attempt=idx + 1)
            provider_inst = resolve_provider_instance(
                provider_name=prov_name,
                model=model_name,
                openrouter_api_key=request.openrouter_api_key,
                gemini_api_key=request.gemini_api_key,
                openai_api_key=request.openai_api_key,
                ollama_base_url=request.ollama_base_url,
                ollama_model=request.ollama_model,
            )

            has_yielded_content = False
            async for chunk in provider_inst.stream_chat(
                messages=request.messages,
                tools=tools if request.enable_tools else None,
                temperature=request.temperature,
            ):
                if chunk.type == "error":
                    last_error = chunk.delta
                    break  # Try next fallback if error occurred
                
                has_yielded_content = True
                yield chunk

            if has_yielded_content:
                return  # Successfully completed streaming

        except Exception as e:
            last_error = str(e)
            logger.warning("provider_stream_attempt_failed", provider=prov_name, model=model_name, error=last_error[:300])

    # If all providers failed
    yield AIChatStreamChunk(
        type="error",
        delta=f"All AI providers failed. Last error: {last_error or 'Unknown failure'}. Please verify your API key in Settings -> AI Engine.",
        provider_used=primary_prov,
    )
