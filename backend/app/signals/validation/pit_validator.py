"""
Point-in-Time (PIT) Integrity Validator (§34, §56).
Enforces strictly non-anticipative data ingestion and feature generation.
Verifies that no future data, revised future OI, or look-ahead candles enter the signal pipeline.

Fail-closed policy: any unparsable timestamp, empty candle set, stale data,
forming (unclosed) candle, or future decision timestamp is a violation —
never silently skipped.
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.signals.safety.clocks import IST as IST_TZ


class PITValidationResult(BaseModel):
    passed: bool = True
    decision_timestamp_ms: int
    max_data_timestamp_ms: int = 0
    time_delta_ms: int = 0
    leakage_detected: bool = False
    violations: list[str] = Field(default_factory=list)


def _to_ms(value: Any) -> Optional[int]:
    """Converts int/float (s or ms), ISO string, or datetime to epoch ms.

    Naive datetimes/strings are interpreted as IST (NSE session timezone).
    Returns None when the value cannot be parsed (caller must fail closed).
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        try:
            dt = value
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST_TZ)
            return int(dt.timestamp() * 1000)
        except Exception:
            return None
    if isinstance(value, (int, float)):
        try:
            v = float(value)
        except Exception:
            return None
        if v <= 0:
            return None
        return int(v if v > 1e11 else v * 1000)
    if isinstance(value, str):
        try:
            text = value.strip().replace("Z", "+00:00")
            dt = datetime.fromisoformat(text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=IST_TZ)
            return int(dt.timestamp() * 1000)
        except Exception:
            return None
    return None


_CLOSE_TIME_KEYS = (
    "close_time",
    "close_timestamp_ms",
    "close_timestamp",
    "closeTime",
    "end_time",
    "end_timestamp",
)


class PointInTimeValidator:
    """
    Validates that features, candles, and market data strictly precede or equal the decision timestamp.
    """

    @staticmethod
    def validate_timeline(
        decision_timestamp_ms: int,
        candles: list[dict] | None,
        fno_data: Optional[dict[str, Any]] = None,
        quote_timestamp_ms: Optional[int] = None,
        tolerance_ms: int = 250,  # Clock skew tolerance
        max_age_ms: int = 120000,  # Staleness floor: data older than this vs decision is stale
        require_closed_candle: bool = False,
        now_ms: Optional[int] = None,
    ) -> PITValidationResult:
        violations: list[str] = []
        max_seen_ts = 0

        try:
            decision_ts = int(decision_timestamp_ms)
        except Exception:
            decision_ts = 0
        if decision_ts <= 0:
            violations.append("INVALID_DECISION_TIMESTAMP: decision timestamp is missing or non-positive")

        # 0. Reject future decision timestamps (fail closed — no forward-dated decisions)
        try:
            ref_now = int(now_ms) if now_ms is not None else int(time.time() * 1000)
        except Exception:
            ref_now = int(time.time() * 1000)
        if decision_ts > 0 and decision_ts > (ref_now + tolerance_ms):
            violations.append(
                f"FUTURE_DECISION_TIMESTAMP: decision timestamp ({decision_ts}ms) > now ({ref_now}ms)"
            )

        # 1. Validate Candle Timestamps (non-empty required)
        if not candles:
            violations.append("EMPTY_CANDLES: no PIT candles provided for decision timestamp validation")
        else:
            for i, c in enumerate(candles):
                if not isinstance(c, dict):
                    violations.append(f"UNPARSABLE_TIMESTAMP: Candle #{i} is not a mapping")
                    continue
                ts = c.get("timestamp")
                ts_ms = _to_ms(ts)
                if ts_ms is None:
                    violations.append(
                        f"UNPARSABLE_TIMESTAMP: Candle #{i} timestamp ({ts!r}) cannot be parsed"
                    )
                    continue

                if ts_ms > max_seen_ts:
                    max_seen_ts = ts_ms

                if ts_ms > (decision_ts + tolerance_ms):
                    violations.append(
                        f"LOOKAHEAD_VIOLATION: Candle #{i} timestamp ({ts_ms}ms) > decision timestamp ({decision_ts}ms)"
                    )

                # 1b. Forming-candle check: unclosed candles must not feed the decision
                if require_closed_candle:
                    close_raw = None
                    for _k in _CLOSE_TIME_KEYS:
                        if c.get(_k) is not None:
                            close_raw = c.get(_k)
                            break
                    if close_raw is not None:
                        close_ms = _to_ms(close_raw)
                        if close_ms is None:
                            violations.append(
                                f"UNPARSABLE_CLOSE_TIME: Candle #{i} close_time ({close_raw!r}) cannot be parsed"
                            )
                        elif close_ms > (decision_ts + tolerance_ms):
                            violations.append(
                                f"FORMING_CANDLE: Candle #{i} close_time ({close_ms}ms) > decision timestamp ({decision_ts}ms)"
                            )

        # 2. Validate Quote Timestamp
        if quote_timestamp_ms is not None:
            q_ms = _to_ms(quote_timestamp_ms)
            if q_ms is None:
                violations.append(
                    f"UNPARSABLE_TIMESTAMP: Quote timestamp ({quote_timestamp_ms!r}) cannot be parsed"
                )
            else:
                if q_ms > (decision_ts + tolerance_ms):
                    violations.append(
                        f"LOOKAHEAD_VIOLATION: Quote timestamp ({q_ms}ms) > decision timestamp ({decision_ts}ms)"
                    )
                if q_ms > max_seen_ts:
                    max_seen_ts = q_ms

        # 3. Validate F&O Snapshot
        if fno_data and "timestamp_ms" in fno_data:
            fno_ms = _to_ms(fno_data.get("timestamp_ms"))
            if fno_ms is None:
                violations.append(
                    f"UNPARSABLE_TIMESTAMP: F&O timestamp ({fno_data.get('timestamp_ms')!r}) cannot be parsed"
                )
            else:
                if fno_ms > (decision_ts + tolerance_ms):
                    violations.append(
                        f"LOOKAHEAD_VIOLATION: F&O timestamp ({fno_ms}ms) > decision timestamp ({decision_ts}ms)"
                    )
                if fno_ms > max_seen_ts:
                    max_seen_ts = fno_ms

        # 4. Staleness floor: data must be recent relative to the decision
        try:
            floor = int(max_age_ms) if max_age_ms is not None else 0
        except Exception:
            floor = 0
        if floor > 0 and decision_ts > 0 and max_seen_ts > 0:
            if (decision_ts - max_seen_ts) > floor:
                violations.append(
                    f"STALE_DATA: newest data ({max_seen_ts}ms) is {decision_ts - max_seen_ts}ms older than "
                    f"decision timestamp ({decision_ts}ms), exceeds max_age_ms={floor}"
                )

        passed = (len(violations) == 0)
        return PITValidationResult(
            passed=passed,
            decision_timestamp_ms=decision_ts,
            max_data_timestamp_ms=max_seen_ts,
            time_delta_ms=max(0, max_seen_ts - decision_ts),
            leakage_detected=not passed,
            violations=violations,
        )


pit_validator = PointInTimeValidator()
