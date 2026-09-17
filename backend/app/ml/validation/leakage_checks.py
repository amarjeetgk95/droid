"""Temporal Leakage Checks for DROID ML Engine.

Implements Section 1.2, Section 8, and Section 23 of the DROID ML Specification.
Enforces strict chronological causality across features, normalization, and labels.
"""
from __future__ import annotations

from typing import Any, Dict, List
from app.ml.features.feature_extractor_v3 import extract_features_v3, TemporalLeakageError


def verify_feature_temporal_integrity(
    instrument: str,
    feature_timestamp_ms: int,
    candles_1m: List[Dict[str, Any]],
    indicators: Dict[str, Any] | None = None,
    options_analytics: Dict[str, Any] | None = None,
    vix_quote: Dict[str, Any] | None = None,
) -> bool:
    """
    Validates that extract_features_v3 never accesses data with timestamp > feature_timestamp_ms.
    Returns True if valid; raises TemporalLeakageError if leakage occurs.
    """
    vec = extract_features_v3(
        instrument=instrument,
        feature_timestamp_ms=feature_timestamp_ms,
        candles_1m=candles_1m,
        indicators=indicators,
        options_analytics=options_analytics,
        vix_quote=vix_quote,
    )
    vec.validate_pit()
    return True


def assert_no_lookahead_in_matrix(timestamps: List[int]) -> bool:
    """Asserts that a sequence of training sample timestamps is strictly monotonically non-decreasing."""
    for i in range(1, len(timestamps)):
        if timestamps[i] < timestamps[i - 1]:
            raise TemporalLeakageError(
                f"Non-chronological ordering detected at index {i}: {timestamps[i]} < {timestamps[i - 1]}"
            )
    return True
