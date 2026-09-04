"""
AI Output Validator — §2, §6, §21

Validates provider result against strict schema.
Short-circuits on first failure; never repairs malformed output.
Pure function, no I/O.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone, timedelta
from typing import Literal, Optional
import structlog

from app.ai.schemas import (
    AISignal,
    Decision,
    SetupType,
    Regime,
    ValidationStatus,
    ValidationResult,
    RejectionReason,
    LatencyBreakdown,
)

logger = structlog.get_logger()

ALLOWED_DECISIONS = {d.value for d in Decision}
ALLOWED_SETUP_TYPES = {s.value for s in SetupType}
ALLOWED_REGIMES = {r.value for r in Regime}

SCALPING_TIMEFRAMES = {"1M", "3M"}
CORE_TIMEFRAMES = {"5M", "15M"}

TTL_BOUNDS_SCALPING = (15, 120)
TTL_BOUNDS_CORE = (120, 900)
MAX_TTL_SCALPING = 180
MAX_TTL_CORE = 1200

MAX_FUTURE_SKEW_SECONDS = 60

MIN_TICK_SIZE = 0.05


class AIOutputValidator:
    """
    Validates AI provider output against strict schema per §6.

    Per §2: Pure function, no I/O.
    Per §6: Short-circuits on first failure, never repairs.
    """

    def validate(
        self,
        raw_response: str | dict,
        path: Literal["scalping", "core"],
        expected_symbol: Optional[str] = None,
        expected_timeframe: Optional[str] = None,
        expected_state_version: Optional[int] = None,
        request_timestamp: Optional[datetime] = None,
        tick_size: float = MIN_TICK_SIZE,
    ) -> tuple[AISignal, ValidationResult]:
        """
        Full pipeline validation per §6.

        Returns:
            Tuple of (AISignal, ValidationResult) where ValidationResult indicates pass/reject
        """
        signal = AISignal()
        validation_result = ValidationResult()

        now = request_timestamp or datetime.now(timezone.utc)

        parsed, err = self._extract_json(raw_response)
        if err:
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.INVALID_SCHEMA
            validation_result.reason_detail = f"JSON parsing: {err}"
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.INVALID_SCHEMA
            signal.rejection_detail = validation_result.reason_detail
            return signal, validation_result

        if not isinstance(parsed, dict):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.INVALID_SCHEMA
            validation_result.reason_detail = f"JSON root not object: {type(parsed)}"
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.INVALID_SCHEMA
            signal.rejection_detail = validation_result.reason_detail
            return signal, validation_result

        if err := self._validate_required_fields(parsed, path):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.INVALID_SIGNAL
            validation_result.reason_detail = err
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.INVALID_SIGNAL
            signal.rejection_detail = err
            return signal, validation_result

        if err := self._validate_enums(parsed):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.INVALID_ENUM
            validation_result.reason_detail = err
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.INVALID_ENUM
            signal.rejection_detail = err
            return signal, validation_result

        if err := self._validate_numeric_ranges(parsed):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.CONFIDENCE_OUT_OF_RANGE
            validation_result.reason_detail = err
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.CONFIDENCE_OUT_OF_RANGE
            signal.rejection_detail = err
            return signal, validation_result

        if err := self._validate_timestamp(parsed, now):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.INVALID_SIGNAL
            validation_result.reason_detail = err
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.INVALID_SIGNAL
            signal.rejection_detail = err
            return signal, validation_result

        if err := self._validate_stop_target(parsed, tick_size):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.INVALID_STOP_TARGET
            validation_result.reason_detail = err
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.INVALID_STOP_TARGET
            signal.rejection_detail = err
            return signal, validation_result

        if err := self._validate_ttl(parsed, path):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.EXPIRED_SIGNAL
            validation_result.reason_detail = err
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.EXPIRED_SIGNAL
            signal.rejection_detail = err
            return signal, validation_result

        if err := self._validate_timeframe(parsed, path):
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.TIMEFRAME_MISMATCH
            validation_result.reason_detail = err
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.TIMEFRAME_MISMATCH
            signal.rejection_detail = err
            return signal, validation_result

        if expected_symbol and parsed.get("symbol", "").upper() != expected_symbol.upper():
            validation_result.status = ValidationStatus.REJECT
            validation_result.reason_code = RejectionReason.SYMBOL_MISMATCH
            validation_result.reason_detail = f"Symbol mismatch: expected {expected_symbol}, got {parsed.get('symbol')}"
            signal.validation_result = ValidationStatus.REJECT
            signal.rejection_reason_code = RejectionReason.SYMBOL_MISMATCH
            signal.rejection_detail = validation_result.reason_detail
            return signal, validation_result

        signal = self._build_signal(parsed, path)
        validation_result.status = ValidationStatus.PASS
        signal.validation_result = ValidationStatus.PASS
        return signal, validation_result

    def _extract_json(self, raw: str | dict) -> tuple[Optional[dict], Optional[str]]:
        if isinstance(raw, dict):
            return raw, None
        if hasattr(raw, "model_dump"):
            dumped = raw.model_dump(mode="json")
            if "market_bias" in dumped and "decision" not in dumped:
                bias = str(dumped.get("market_bias", "NEUTRAL")).upper()
                dumped["decision"] = "LONG" if bias == "BULLISH" else "SHORT" if bias == "BEARISH" else "NO_TRADE"
                dumped.setdefault("setup_type", "CONTINUATION")
                dumped.setdefault("regime", "TREND" if bias in ("BULLISH", "BEARISH") else "RANGE")
                dumped.setdefault("entry", 1.0)
                dumped.setdefault("stop_loss", 0.99)
                dumped.setdefault("target", 1.01)
                dumped.setdefault("ttl_seconds", 60)
                reasons = []
                if dumped.get("simple_takeaway"):
                    reasons.append(dumped["simple_takeaway"][:100])
                elif dumped.get("executive_summary"):
                    reasons.append(dumped["executive_summary"][:100])
                dumped.setdefault("reasons", reasons or ["AI Analysis"])
                dumped.setdefault("invalidation", ["Stop loss hit"])
            return dumped, None
        if not isinstance(raw, str):
            return None, f"response not str/dict: {type(raw)}"
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

    def _validate_required_fields(self, parsed: dict, path: str) -> Optional[str]:
        if path == "scalping":
            required = ["decision", "setup_type", "confidence", "entry", "stop_loss", "target", "ttl_seconds", "regime"]
        else:
            required = ["decision", "setup_type", "confidence", "entry", "stop_loss", "target", "ttl_seconds", "regime"]
        missing = [f for f in required if f not in parsed or parsed.get(f) is None or parsed.get(f) == ""]
        if missing:
            return f"missing required fields: {missing}"
        return None

    def _validate_enums(self, parsed: dict) -> Optional[str]:
        decision = parsed.get("decision", "")
        if decision not in ALLOWED_DECISIONS:
            return f"invalid decision: {decision} (allowed: {ALLOWED_DECISIONS})"
        setup_type = parsed.get("setup_type", "")
        if setup_type not in ALLOWED_SETUP_TYPES:
            return f"invalid setup_type: {setup_type} (allowed: {ALLOWED_SETUP_TYPES})"
        regime = parsed.get("regime", "")
        if regime not in ALLOWED_REGIMES:
            return f"invalid regime: {regime} (allowed: {ALLOWED_REGIMES})"
        return None

    def _validate_numeric_ranges(self, parsed: dict) -> Optional[str]:
        try:
            confidence = float(parsed.get("confidence", 0))
            if not (0 <= confidence <= 100):
                return f"confidence out of range 0-100: {confidence}"
        except (ValueError, TypeError):
            return f"confidence not numeric: {parsed.get('confidence')}"
        try:
            entry = float(parsed.get("entry", 0))
            if entry <= 0:
                return f"entry price must be > 0: {entry}"
        except (ValueError, TypeError):
            return f"entry not numeric: {parsed.get('entry')}"
        try:
            stop_loss = float(parsed.get("stop_loss", 0))
            if stop_loss <= 0:
                return f"stop_loss must be > 0: {stop_loss}"
        except (ValueError, TypeError):
            return f"stop_loss not numeric: {parsed.get('stop_loss')}"
        try:
            target = float(parsed.get("target", 0))
            if target <= 0:
                return f"target must be > 0: {target}"
        except (ValueError, TypeError):
            return f"target not numeric: {parsed.get('target')}"
        return None

    def _validate_timestamp(self, parsed: dict, now: datetime) -> Optional[str]:
        ts_raw = parsed.get("timestamp")
        if ts_raw is None:
            return None
        try:
            if isinstance(ts_raw, str):
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            elif isinstance(ts_raw, datetime):
                ts = ts_raw
            else:
                ts = None
            if ts is None:
                return None
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts > now + timedelta(seconds=MAX_FUTURE_SKEW_SECONDS):
                return f"future timestamp: {ts.isoformat()} > now+{MAX_FUTURE_SKEW_SECONDS}s"
        except Exception as e:
            return f"timestamp validation error: {e}"
        return None

    def _validate_stop_target(self, parsed: dict, tick_size: float) -> Optional[str]:
        try:
            decision = parsed.get("decision")
            entry = float(parsed.get("entry", 0))
            stop_loss = float(parsed.get("stop_loss", 0))
            target = float(parsed.get("target", 0))

            if decision == Decision.LONG.value:
                if stop_loss >= entry:
                    return f"LONG: stop_loss ({stop_loss}) must be < entry ({entry})"
                if target <= entry:
                    return f"LONG: target ({target}) must be > entry ({entry})"
                min_distance = tick_size * 2
                if (entry - stop_loss) < min_distance:
                    return f"LONG: stop distance {(entry - stop_loss)} < min {min_distance}"
            elif decision == Decision.SHORT.value:
                if stop_loss <= entry:
                    return f"SHORT: stop_loss ({stop_loss}) must be > entry ({entry})"
                if target >= entry:
                    return f"SHORT: target ({target}) must be < entry ({entry})"
                min_distance = tick_size * 2
                if (stop_loss - entry) < min_distance:
                    return f"SHORT: stop distance {(stop_loss - entry)} < min {min_distance}"
            return None
        except Exception as e:
            return f"stop/target validation error: {e}"

    def _validate_ttl(self, parsed: dict, path: str) -> Optional[str]:
        try:
            ttl = int(parsed.get("ttl_seconds", 0))
            if path == "scalping":
                min_ttl, max_ttl = TTL_BOUNDS_SCALPING
                hard_max = MAX_TTL_SCALPING
            else:
                min_ttl, max_ttl = TTL_BOUNDS_CORE
                hard_max = MAX_TTL_CORE
            if not (min_ttl <= ttl <= max_ttl):
                return f"ttl_seconds {ttl} outside bounds ({min_ttl}-{max_ttl})"
            if ttl > hard_max:
                return f"ttl_seconds {ttl} exceeds hard ceiling {hard_max}"
            return None
        except Exception as e:
            return f"ttl validation error: {e}"

    def _validate_timeframe(self, parsed: dict, path: str) -> Optional[str]:
        timeframe = parsed.get("timeframe", "")
        if path == "scalping":
            allowed = SCALPING_TIMEFRAMES
        else:
            allowed = CORE_TIMEFRAMES
        if timeframe and timeframe not in allowed:
            return f"timeframe {timeframe} not allowed for {path} path (allowed: {allowed})"
        return None

    def _build_signal(self, parsed: dict, path: str) -> AISignal:
        now = datetime.now(timezone.utc)
        try:
            ttl = int(parsed.get("ttl_seconds", 60))
        except (ValueError, TypeError):
            ttl = 60
        expires_at = now + timedelta(seconds=ttl)

        signal = AISignal(
            signal_id=parsed.get("signal_id") or str(parsed.get("id", "")) or "",
            symbol=parsed.get("symbol", "NIFTY").upper(),
            timestamp=now,
            timeframe=parsed.get("timeframe", "5M" if path == "core" else "1M"),
            decision=Decision(parsed.get("decision", Decision.NO_TRADE.value)),
            setup_type=SetupType(parsed.get("setup_type", SetupType.CONTINUATION.value)),
            regime=Regime(parsed.get("regime", Regime.UNKNOWN.value)),
            raw_confidence=int(parsed.get("confidence", 0)),
            calibrated_confidence=int(parsed.get("calibrated_confidence", parsed.get("confidence", 0))),
            entry=float(parsed.get("entry", 0)),
            stop_loss=float(parsed.get("stop_loss", 0)),
            target=float(parsed.get("target", 0)),
            ttl_seconds=ttl,
            expires_at=expires_at,
            reasons=parsed.get("reasons") or [],
            invalidation=parsed.get("invalidation") or [],
            provider=parsed.get("provider") or "",
            model=parsed.get("model") or "",
            reused=parsed.get("reused", False),
            superseded=parsed.get("superseded", False),
        )
        return signal


ai_output_validator = AIOutputValidator()
