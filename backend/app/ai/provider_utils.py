"""
Shared helpers for provider response handling.

Kept provider-agnostic (no HTTP clients) so direct providers, OpenAI-compatible
providers and gateway providers can all reuse the same JSON extraction,
market_bias normalization and analyze() plumbing.
"""
from __future__ import annotations

import json
from typing import Any

_MARKET_BIASES = ("BULLISH", "BEARISH", "NEUTRAL", "VOLATILE")


def extract_json_object(content: Any, provider_label: str) -> Any:
    """
    Robustly parse an LLM response into JSON.

    Handles markdown code fences and prose-wrapped JSON objects. Non-string
    content (already-parsed dicts/lists) is returned untouched. Raises
    ValueError with a provider_label-prefixed message on failure.
    """
    if not isinstance(content, str):
        return content

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
        return json.loads(c)
    except json.JSONDecodeError:
        start_idx = c.find("{")
        end_idx = c.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            try:
                return json.loads(c[start_idx : end_idx + 1])
            except json.JSONDecodeError as je:
                raise ValueError(f"{provider_label} returned non-JSON content: {c[:400]} (json error: {je})")
        raise ValueError(f"{provider_label} returned non-JSON content: {c[:400]}")


def normalize_market_bias(value: Any) -> str:
    """Normalize a provider market_bias into BULLISH/BEARISH/NEUTRAL/VOLATILE."""
    raw = str(value if value is not None else "NEUTRAL").upper()
    if raw in _MARKET_BIASES:
        return raw
    if "BULL" in raw:
        return "BULLISH"
    if "BEAR" in raw:
        return "BEARISH"
    return "NEUTRAL"


async def analyze_market_state(provider, market_state: dict, task: str) -> dict:
    """Shared AIProvider.analyze() implementation: grounded prompt -> generate_analysis -> dict."""
    from app.ai.prompt_builder import build_system_prompt

    system_prompt = build_system_prompt()
    user_prompt = f"Task: {task}\nMarketState: {json.dumps(market_state, default=str)}"
    insight = await provider.generate_analysis(market_state.get("symbol", "NIFTY"), system_prompt, user_prompt)
    return insight.model_dump(mode="json")
