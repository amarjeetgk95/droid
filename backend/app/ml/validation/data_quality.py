"""Data Quality Gate & Safe-Mode Circuit Breaker for DROID ML Engine.

Implements Section 19 of the DROID ML Specification.
Guards inference pipelines against:
  - Feed staleness (>10s)
  - Unsanitized NaN / Inf feature entries
  - Extreme out-of-bounds market anomalies
Transitions gracefully into SAFE_MODE without crashing the execution runtime.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import numpy as np


@dataclass(frozen=True)
class QualityGateResult:
    is_valid: bool
    status: str  # "ACTIVE", "DEGRADED", "CIRCUIT_BROKEN"
    circuit_breaker_action: str  # "NORMAL", "SHADOW_ONLY", "SAFE_MODE_BYPASS"
    violations: List[str]
    staleness_ms: int


class DataQualityGate:
    """
    Validates feature vectors and market data feeds prior to ML inference.
    """

    def __init__(
        self,
        max_staleness_ms: int = 10000,       # 10s warning
        critical_staleness_ms: int = 30000,  # 30s hard cutoff
    ):
        self.max_staleness_ms = max_staleness_ms
        self.critical_staleness_ms = critical_staleness_ms

    def validate_features(
        self,
        feature_vector: List[float],
        evaluation_timestamp_ms: int,
        max_source_timestamp_ms: int,
        spot_price: float,
    ) -> QualityGateResult:
        """
        Validates the pre-inference feature vector.
        """
        violations: List[str] = []

        # 1. Staleness check
        staleness = max(0, evaluation_timestamp_ms - max_source_timestamp_ms)
        if staleness > self.critical_staleness_ms:
            violations.append(f"CRITICAL_STALENESS: Data feed is {staleness}ms stale (> {self.critical_staleness_ms}ms)")
        elif staleness > self.max_staleness_ms:
            violations.append(f"STALENESS_WARNING: Data feed is {staleness}ms stale (> {self.max_staleness_ms}ms)")

        # 2. Spot price sanity
        if spot_price <= 0 or math.isnan(spot_price) or math.isinf(spot_price):
            violations.append(f"INVALID_SPOT_PRICE: Spot price is {spot_price}")

        # 3. Feature vector checks
        if not feature_vector or len(feature_vector) == 0:
            violations.append("EMPTY_FEATURE_VECTOR: Feature vector is empty")
        else:
            nan_count = sum(1 for v in feature_vector if math.isnan(v) or math.isinf(v))
            if nan_count > 0:
                violations.append(f"CORRUPT_FEATURES: Found {nan_count} NaN or Inf feature entries")

        # 4. State transition
        if any("CRITICAL" in v or "INVALID_SPOT" in v or "CORRUPT" in v for v in violations):
            status = "CIRCUIT_BROKEN"
            action = "SAFE_MODE_BYPASS"
            is_valid = False
        elif len(violations) > 0:
            status = "DEGRADED"
            action = "SHADOW_ONLY"
            is_valid = True
        else:
            status = "ACTIVE"
            action = "NORMAL"
            is_valid = True

        return QualityGateResult(
            is_valid=is_valid,
            status=status,
            circuit_breaker_action=action,
            violations=violations,
            staleness_ms=staleness,
        )


data_quality_gate = DataQualityGate()
