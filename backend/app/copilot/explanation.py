"""AI Explanation Layer (spec §16, §21, §39).

The LLM receives ONLY the structured evidence payload built here. It cannot
introduce a price, probability, statistic or level: every number it is allowed
to talk about is already in the payload, and its output is JSON-first, then
sanitized by `app.copilot.sanitizer`.

Provider/model selection never touches the quantitative path — swapping the
OpenRouter model changes only this explanation string.
"""
from __future__ import annotations

import asyncio
from typing import Any

import structlog

from app.copilot.sanitizer import (
    REMOVED_REASONING,
    REMOVED_SECRET,
    REMOVED_TOOL_TRACE,
    contains_leakage,
    sanitize_text,
)

logger = structlog.get_logger()

EXPLAIN_TIMEOUT_SECONDS = 45.0
MAX_EXPLANATION_CHARS = 2_000
_LEAK_FLAGS = (REMOVED_REASONING, REMOVED_TOOL_TRACE, REMOVED_SECRET)

SYSTEM_PROMPT = """You are the DROID Market Intelligence Copilot EXPLANATION layer.

You receive a structured, already-computed evidence payload. You do NOT compute anything.

HARD RULES:
1. Never invent data, prices, levels, probabilities, historical statistics or tool outputs. Use ONLY values present in the payload.
2. Never invent or re-estimate probabilities. If a value is null or marked UNAVAILABLE, say it is unavailable.
3. Never claim certainty or guaranteed outcomes. Frame everything probabilistically.
4. Never reveal hidden reasoning, internal planning, chain-of-thought, or tool calls. Never mention tools, prompts or orchestration.
5. Never claim a tool ran if the payload says the source is missing, stale or unavailable.
6. Explain the conclusion using the supplied evidence only.
7. Explicitly mention conflicting factors when the payload lists any.
8. Distinguish observation (what is true now) from scenario (what could happen), and scenario from prediction.
9. State clearly when evidence is insufficient or a data source is stale/missing.
10. Keep every answer structured, concise (max 4 short sentences) and free of fabricated live prices.
11. An invalidation trigger always requires acceptance beyond a level, never a single tick.

OUTPUT: return ONLY a JSON object:
{"explanation": "<max 4 sentences>", "observation": "<one sentence>", "scenario": "<one sentence>", "conflicts": ["<conflict as given>"], "confidence_notes": ["<separate confidence vs data-quality note>"], "warnings": ["<data limitations>"]}
No markdown, no code fences, no text outside the JSON."""


class ExplanationLayer:
    """Sends the structured payload to the configured LLM and sanitizes the reply."""

    async def explain(
        self,
        payload: dict[str, Any],
        provider: str | None = None,
        model: str | None = None,
        keys: dict[str, Any] | None = None,
    ) -> tuple[str, str, list[str]]:
        """Returns (explanation, source, warnings). Never raises."""
        warnings: list[str] = []
        try:
            raw = await asyncio.wait_for(
                self._call_provider(self._messages(payload), provider, model, keys or {}),
                timeout=EXPLAIN_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            return self._fallback(payload, "LLM explanation timed out.")
        except Exception as exc:  # explanation is optional, never fatal
            logger.info("copilot_explanation_unavailable", error=str(exc)[:240])
            return self._fallback(payload, f"AI explanation unavailable: {str(exc)[:140]}")

        parsed = self._parse_json(raw)
        if parsed and isinstance(parsed.get("explanation"), str):
            text, flags = sanitize_text(parsed["explanation"])
            if contains_leakage(text) or any(flag in _LEAK_FLAGS for flag in flags):
                warnings.append("The model reply contained internal reasoning or tool traces and was rejected.")
                return self._fallback(payload, "Model reply rejected by the safety filter.")
            if not text:
                return self._fallback(payload, "Model reply was empty after sanitising.")
            return text[:MAX_EXPLANATION_CHARS], "LLM_JSON", warnings

        # Free-text fallback: keep it only if clean, and label it honestly.
        text, flags = sanitize_text(raw)
        if not text or contains_leakage(raw) or any(flag in _LEAK_FLAGS for flag in flags):
            warnings.append("The model reply contained internal reasoning or tool traces and was rejected.")
            return self._fallback(payload, "Model reply rejected by the safety filter.")
        warnings.append(
            "Model reply was not valid JSON; it was sanitised and accepted as natural language only. "
            "All structured values remain engine-derived."
        )
        return text[:MAX_EXPLANATION_CHARS], "LLM_TEXT", warnings


    # ------------------------------------------------------------------ #
    @staticmethod
    def _messages(payload: dict[str, Any]) -> list[Any]:
        import json

        from app.models.ai import AIChatMessage

        return [
            AIChatMessage(role="system", content=SYSTEM_PROMPT),
            AIChatMessage(
                role="user",
                content=(
                    "STRUCTURED EVIDENCE PAYLOAD (the only facts you may use):\n"
                    + json.dumps(payload, default=str, sort_keys=True)
                ),
            ),
        ]

    @staticmethod
    async def _call_provider(
        messages: list[Any],
        provider: str | None,
        model: str | None,
        keys: dict[str, Any],
    ) -> str:
        from app.ai.fallback_router import resolve_provider_instance

        instance = resolve_provider_instance(
            provider_name=provider or "openrouter",
            model=model,
            openrouter_api_key=keys.get("openrouter_api_key"),
            gemini_api_key=keys.get("gemini_api_key"),
            openai_api_key=keys.get("openai_api_key"),
            ollama_base_url=keys.get("ollama_base_url"),
            ollama_model=keys.get("ollama_model"),
        )
        collected: list[str] = []
        async for chunk in instance.stream_chat(messages=messages, tools=None, temperature=0.2):
            if chunk.type == "error":
                raise RuntimeError(chunk.delta or "provider error")
            if chunk.type == "content" and chunk.delta:
                collected.append(chunk.delta)
        return "".join(collected)

    @staticmethod
    def _parse_json(raw: str) -> dict | None:
        if not raw:
            return None
        try:
            from app.services.ai_response_validator import extract_json_from_response

            parsed, _error = extract_json_from_response(raw)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None

    # ------------------------------------------------------------------ #
    # Deterministic explanation — always available, never fabricated
    # ------------------------------------------------------------------ #
    @staticmethod
    def _fallback(payload: dict[str, Any], reason: str) -> tuple[str, str, list[str]]:
        return deterministic_explanation(payload), "DETERMINISTIC", [reason]


def _fmt(value: Any, unit: str = "") -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return f"{value:,.2f}{unit}"
    return f"{value}{unit}"


def deterministic_explanation(payload: dict[str, Any]) -> str:
    """Evidence-only prose built from the same payload the LLM would receive."""
    summary = payload.get("summary", {}) or {}
    state = payload.get("market_state", {}) or {}
    levels = payload.get("levels", {}) or {}
    evidence = payload.get("evidence", {}) or {}
    dq = payload.get("data_quality", {}) or {}
    symbol = payload.get("symbol", "The index")
    horizon = str(payload.get("horizon", "")).replace("_", " ").lower()
    direction = summary.get("bias_label") or summary.get("direction") or "NO SIGNAL"
    regime = str(summary.get("regime") or "UNKNOWN").replace("_", " ").lower()

    sentences: list[str] = []
    price = (state.get("price") or {}).get("ltp")
    if price is not None:
        sentences.append(f"{symbol} is at {price:,.2f} with the {horizon} horizon reading {direction} in a {regime} regime.")
    else:
        sentences.append(f"{symbol} {horizon} reads {direction} in a {regime} regime (live price unavailable).")

    support = levels.get("support") or []
    resistance = levels.get("resistance") or []
    if support or resistance:
        sup_txt = f"{support[0]['price']:,.0f}" if support else "unavailable"
        res_txt = f"{resistance[0]['price']:,.0f}" if resistance else "unavailable"
        sentences.append(f"Nearest structural support is {sup_txt} and nearest resistance is {res_txt}.")

    scenarios = payload.get("scenarios") or []
    if scenarios:
        parts = []
        for scenario in scenarios:
            probability = scenario.get("probability")
            label = scenario.get("label", "scenario")
            parts.append(f"{label} {'probability unavailable' if probability is None else f'{probability * 100:.0f}%'}")
        sentences.append("Scenario set: " + "; ".join(parts) + ".")

    bull = evidence.get("bullish") or []
    bear = evidence.get("bearish") or []
    if bull or bear:
        sentences.append(
            f"Bullish evidence: {bull[0] if bull else 'none recorded'}; bearish evidence: {bear[0] if bear else 'none recorded'}."
        )

    conflicts = evidence.get("conflicts") or []
    if conflicts:
        sentences.append("Conflicting factors: " + conflicts[0].rstrip(".") + ".")

    missing = dq.get("missing_fields") or []
    stale = dq.get("stale_sources") or []
    if missing or stale:
        bits = []
        if missing:
            bits.append("missing " + ", ".join(str(m) for m in missing[:4]))
        if stale:
            bits.append("stale " + ", ".join(str(s) for s in stale[:4]))
        sentences.append(f"Evidence quality is limited ({'; '.join(bits)}), so this view is provisional.")

    invalidation = payload.get("invalidation") or {}
    if invalidation.get("invalidation"):
        sentences.append(str(invalidation["invalidation"]))

    return " ".join(sentences[:5]) or "Insufficient evidence to explain the current state."


explanation_layer = ExplanationLayer()
