"""
Model Capability Registry — §18

Store per-model capabilities where available:
{
  "model_id": "inclusionai/ling-3.0-flash-fin:free",
  "free": true,
  "supports_structured_outputs": false,
  "supports_tools": true,
  "context_length": 262144
}

Request layer chooses appropriate protocol:
structured outputs supported -> native structured response
unsupported -> prompted JSON + local validation

Do not send unsupported parameters.
"""
from __future__ import annotations

from typing import Any

# Known models that REJECT structured outputs (via live provider test)
# From §17: Ling 3.0 Flash Fin rejects response_format={"type":"json_object"}
KNOWN_NO_STRUCTURED_OUTPUTS: set[str] = {
    "inclusionai/ling-3.0-flash-fin:free",
    "inclusionai/ling-3.0-flash-fin",
    "inclusionai/ling-3-flash-fin:free",
    "inclusionai/ling-flash-fin:free",
}

# Known capabilities registry (can be extended dynamically from OpenRouter metadata)
_CAPABILITY_OVERRIDES: dict[str, dict[str, Any]] = {
    "inclusionai/ling-3.0-flash-fin:free": {
        "supports_structured_outputs": False,
        "supports_tools": True,
        "context_length": 262144,
        "free": True,
    },
    "inclusionai/ling-3.0-flash-fin": {
        "supports_structured_outputs": False,
        "supports_tools": True,
        "context_length": 262144,
        "free": False,
    },
}


def get_model_capabilities(model_id: str, raw_metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Return capability dict for model_id.
    Priority: explicit override > raw_metadata > heuristic.
    """
    mid = (model_id or "").strip()
    lower = mid.lower()

    # Check override
    if mid in _CAPABILITY_OVERRIDES:
        return {**_CAPABILITY_OVERRIDES[mid], "model_id": mid}
    # Case-insensitive fallback
    for k, v in _CAPABILITY_OVERRIDES.items():
        if k.lower() == lower:
            return {**v, "model_id": mid}

    # Heuristic: if model_id in KNOWN_NO_STRUCTURED_OUTPUTS
    if lower in {k.lower() for k in KNOWN_NO_STRUCTURED_OUTPUTS}:
        return {
            "model_id": mid,
            "free": ":free" in lower,
            "supports_structured_outputs": False,
            "supports_tools": True,
            "context_length": (raw_metadata or {}).get("context_length", 8192),
        }

    # From raw_metadata if provided (from OpenRouter catalog)
    if raw_metadata:
        supported_params = raw_metadata.get("supported_parameters") or []
        supports_structured = any("response_format" in str(p).lower() or "structured" in str(p).lower() for p in supported_params)
        # Some OpenRouter models expose supported_parameters including "response_format"
        # If not explicitly listed, assume supports structured outputs unless known bad
        # But be conservative: if model is free via Novita provider, many reject structured outputs
        # We use available metadata; otherwise assume True for modern models
        # Use supported_tools detection from catalog
        supports_tools = any("tool" in str(p).lower() for p in supported_params)
        return {
            "model_id": mid,
            "free": raw_metadata.get("is_free", ":free" in lower),
            "supports_structured_outputs": bool(supports_structured) if supported_params else True,
            "supports_tools": bool(supports_tools) if supported_params else False,
            "context_length": raw_metadata.get("context_length", 8192),
        }

    # Default: assume supports structured outputs
    return {
        "model_id": mid,
        "free": ":free" in lower,
        "supports_structured_outputs": True,
        "supports_tools": False,
        "context_length": 8192,
    }


def should_use_structured_outputs(model_id: str, raw_metadata: dict[str, Any] | None = None) -> bool:
    caps = get_model_capabilities(model_id, raw_metadata)
    return bool(caps.get("supports_structured_outputs", True))


def validate_no_unsupported_params(model_id: str, payload: dict, raw_metadata: dict[str, Any] | None = None) -> dict:
    """
    Strip unsupported params based on capabilities.
    Currently strips response_format if not supported.
    """
    if not should_use_structured_outputs(model_id, raw_metadata):
        payload = {k: v for k, v in payload.items() if k != "response_format"}
    return payload
