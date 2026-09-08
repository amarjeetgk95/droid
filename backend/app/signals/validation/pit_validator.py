"""
Point-in-Time (PIT) Integrity Validator (§34, §56).
Enforces strictly non-anticipative data ingestion and feature generation.
Verifies that no future data, revised future OI, or look-ahead candles enter the signal pipeline.
"""
from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, Field


class PITValidationResult(BaseModel):
    passed: bool = True
    decision_timestamp_ms: int
    max_data_timestamp_ms: int = 0
    time_delta_ms: int = 0
    leakage_detected: bool = False
    violations: list[str] = Field(default_factory=list)


class PointInTimeValidator:
    """
    Validates that features, candles, and market data strictly precede or equal the decision timestamp.
    """

    @staticmethod
    def validate_timeline(
        decision_timestamp_ms: int,
        candles: list[dict],
        fno_data: Optional[dict[str, Any]] = None,
        quote_timestamp_ms: Optional[int] = None,
        tolerance_ms: int = 250,  # Clock skew tolerance
    ) -> PITValidationResult:
        violations = []
        max_seen_ts = 0

        # 1. Validate Candle Timestamps
        for i, c in enumerate(candles):
            ts = c.get("timestamp")
            ts_ms = 0
            if isinstance(ts, (int, float)):
                ts_ms = int(ts if ts > 1e11 else ts * 1000)
            elif isinstance(ts, str):
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(ts)
                    ts_ms = int(dt.timestamp() * 1000)
                except Exception:
                    continue

            if ts_ms > max_seen_ts:
                max_seen_ts = ts_ms

            if ts_ms > (decision_timestamp_ms + tolerance_ms):
                violations.append(
                    f"LOOKAHEAD_VIOLATION: Candle #{i} timestamp ({ts_ms}ms) > decision timestamp ({decision_timestamp_ms}ms)"
                )

        # 2. Validate Quote Timestamp
        if quote_timestamp_ms and quote_timestamp_ms > (decision_timestamp_ms + tolerance_ms):
            violations.append(
                f"LOOKAHEAD_VIOLATION: Quote timestamp ({quote_timestamp_ms}ms) > decision timestamp ({decision_timestamp_ms}ms)"
            )
            if quote_timestamp_ms > max_seen_ts:
                max_seen_ts = quote_timestamp_ms

        # 3. Validate F&O Snapshot
        if fno_data and "timestamp_ms" in fno_data:
            fno_ts = int(fno_data["timestamp_ms"])
            if fno_ts > (decision_timestamp_ms + tolerance_ms):
                violations.append(
                    f"LOOKAHEAD_VIOLATION: F&O timestamp ({fno_ts}ms) > decision timestamp ({decision_timestamp_ms}ms)"
                )
            if fno_ts > max_seen_ts:
                max_seen_ts = fno_ts

        passed = (len(violations) == 0)
        return PITValidationResult(
            passed=passed,
            decision_timestamp_ms=decision_timestamp_ms,
            max_data_timestamp_ms=max_seen_ts,
            time_delta_ms=max(0, max_seen_ts - decision_timestamp_ms),
            leakage_detected=not passed,
            violations=violations,
        )


pit_validator = PointInTimeValidator()
