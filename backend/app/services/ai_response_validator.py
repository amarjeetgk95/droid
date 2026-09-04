"""
AI Response Validation — §22

Pipeline:
AI response → JSON parsing → Schema validation → Enum validation → Confidence range →
Required fields → Type validation → State version validation → Timestamp validation

Reject:
invalid JSON, missing fields, invalid bias, confidence <0, confidence >100,
invalid types, wrong state_version, future timestamp, malformed response.

An invalid response must never reach the risk engine.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

from pydantic import BaseModel, Field, ValidationError

# Allowed bias per §20
ALLOWED_BIASES = ("BUY", "SELL", "HOLD", "NO_TRADE", "WAIT_FOR_CONFIRMATION")
# Alternative legacy biases for mapping (BULLISH etc. mapped to BUY/SELL where applicable for validation layer 2)
LEGACY_BIAS_MAP = {
    "BULLISH": "BUY",
    "BEARISH": "SELL",
    "NEUTRAL": "HOLD",
    "VOLATILE": "WAIT_FOR_CONFIRMATION",
}


class ConfidenceBreakdown(BaseModel):
    technical_alignment: float = Field(ge=0, le=100)
    forecast_alignment: float = Field(ge=0, le=100)
    orderflow_alignment: float = Field(ge=0, le=100)
    news_alignment: float = Field(ge=0, le=100)
    overall: float = Field(ge=0, le=100)


class AIValidatedResponse(BaseModel):
    bias: str = Field(pattern="^(BUY|SELL|HOLD|NO_TRADE|WAIT_FOR_CONFIRMATION)$")
    confidence_breakdown: ConfidenceBreakdown
    primary_scenario: str = Field(min_length=1)
    key_invalidation_theme: str = Field(min_length=1)
    state_version: int | None = None
    timestamp: datetime | None = None
    # Allow extra for backward compat with existing insights
    model_config = {"extra": "allow"}


class AIResponseValidationResult:
    def __init__(self, valid: bool, parsed: dict | None = None, error: str | None = None, validated: AIValidatedResponse | None = None):
        self.valid = valid
        self.parsed = parsed
        self.error = error
        self.validated = validated


def extract_json_from_response(raw: str) -> tuple[dict | None, str | None]:
    """
    Strict JSON extraction: strip markdown fences, parse.
    Returns (dict, error)
    """
    if not isinstance(raw, str):
        if isinstance(raw, dict):
            return raw, None
        return None, "response not str/dict"
    c = raw.strip()
    if not c:
        return None, "empty response"
    if c.startswith("```"):
        parts = c.split("```")
        if len(parts) >= 2:
            c = parts[1]
            if c.lstrip().startswith("json"):
                c = c.lstrip()[4:]
        c = c.strip()
        if not c:
            return None, "empty after fence strip"
    try:
        parsed = json.loads(c)
        if not isinstance(parsed, dict):
            return None, f"JSON root not object: {type(parsed)}"
        return parsed, None
    except json.JSONDecodeError as e:
        return None, f"invalid JSON: {e.msg} at {e.pos}"


def validate_ai_response(
    raw_response: str | dict,
    expected_state_version: int | None = None,
    max_future_skew_seconds: int = 60,
) -> AIResponseValidationResult:
    """
    Full pipeline per §22.
    """
    # 1. JSON parsing
    if isinstance(raw_response, dict):
        parsed = raw_response
    else:
        parsed, err = extract_json_from_response(raw_response)
        if err:
            return AIResponseValidationResult(valid=False, error=f"JSON parsing: {err}")

    # 2. Required fields check (for new schema §17 example)
    # Support both new bias schema and legacy AIInsightResponse schema
    # New required: bias, confidence_breakdown, primary_scenario, key_invalidation_theme
    # Legacy required: market_bias, confidence, executive_summary etc.
    # We validate either; if new present, enforce new strict
    has_new_bias = "bias" in parsed
    has_legacy_bias = "market_bias" in parsed

    if has_new_bias:
        # Use Pydantic strict
        try:
            # Check bias enum
            bias_val = parsed.get("bias")
            if isinstance(bias_val, str):
                bias_val = bias_val.strip().upper()
                # Map legacy if needed
                if bias_val in LEGACY_BIAS_MAP:
                    bias_val = LEGACY_BIAS_MAP[bias_val]
                parsed["bias"] = bias_val
            # Validate confidence breakdown ranges already via model
            validated = AIValidatedResponse.model_validate(parsed)
        except ValidationError as e:
            return AIResponseValidationResult(valid=False, parsed=parsed, error=f"Schema validation: {e}")
        except Exception as e:
            return AIResponseValidationResult(valid=False, parsed=parsed, error=f"Type validation: {e}")

        # 3. Confidence range already via pydantic (0-100)

        # 4. State version validation (§6)
        if expected_state_version is not None:
            resp_sv = parsed.get("state_version") or getattr(validated, "state_version", None)
            if resp_sv is None:
                # If response doesn't contain state_version, we associate externally; check via validated
                # For strict, require presence; but if not present we cannot validate – mark invalid unless caller associates
                # Spec says AI response must contain or be associated with that state version.
                # So if missing, we check association separately; here we just warn but not fail if expected provided but missing in json?
                # For safety, fail if expected and not present
                return AIResponseValidationResult(valid=False, parsed=parsed, error=f"wrong state_version: expected {expected_state_version} but response has no state_version")
            try:
                if int(resp_sv) != int(expected_state_version):
                    return AIResponseValidationResult(valid=False, parsed=parsed, error=f"wrong state_version: expected {expected_state_version}, got {resp_sv}")
            except Exception:
                return AIResponseValidationResult(valid=False, parsed=parsed, error=f"state_version type invalid: {resp_sv}")

        # 5. Timestamp validation: not in future beyond skew
        ts_raw = parsed.get("timestamp")
        if ts_raw:
            try:
                if isinstance(ts_raw, str):
                    ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                elif isinstance(ts_raw, datetime):
                    ts = ts_raw
                else:
                    ts = None
                if ts:
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    now = datetime.now(timezone.utc)
                    if ts > now + timedelta(seconds=max_future_skew_seconds):
                        return AIResponseValidationResult(valid=False, parsed=parsed, error=f"future timestamp: {ts.isoformat()} > now+{max_future_skew_seconds}s")
            except Exception as e:
                return AIResponseValidationResult(valid=False, parsed=parsed, error=f"timestamp validation: {e}")

        return AIResponseValidationResult(valid=True, parsed=parsed, validated=validated)

    elif has_legacy_bias:
        # Legacy insight validation (market_bias, confidence)
        required_legacy = ["market_bias", "confidence", "executive_summary", "options_interpretation", "futures_flow_analysis", "regime_and_levels", "recommended_strategy_framework", "risk_management_notes"]
        missing = [f for f in required_legacy if f not in parsed or parsed.get(f) in (None, "")]
        if missing:
            return AIResponseValidationResult(valid=False, parsed=parsed, error=f"missing fields: {missing}")
        bias = str(parsed.get("market_bias", "")).strip().upper()
        if bias not in ("BULLISH", "BEARISH", "NEUTRAL", "VOLATILE"):
            return AIResponseValidationResult(valid=False, parsed=parsed, error=f"invalid bias {bias}")
        try:
            conf = float(parsed.get("confidence"))
            if not math.isfinite(conf) or not (0 <= conf <= 100):
                return AIResponseValidationResult(valid=False, parsed=parsed, error=f"confidence out of range 0-100: {conf}")
        except Exception as e:
            return AIResponseValidationResult(valid=False, parsed=parsed, error=f"confidence type: {e}")

        # Type validation passed; state version & timestamp if present
        if expected_state_version is not None:
            resp_sv = parsed.get("state_version")
            if resp_sv is not None and int(resp_sv) != int(expected_state_version):
                return AIResponseValidationResult(valid=False, parsed=parsed, error=f"wrong state_version: expected {expected_state_version}, got {resp_sv}")
        return AIResponseValidationResult(valid=True, parsed=parsed, validated=None)

    else:
        return AIResponseValidationResult(valid=False, parsed=parsed, error="missing bias/market_bias field")


# For import convenience
from datetime import timedelta
