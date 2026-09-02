"""
Point-In-Time (PIT) & Leakage CI Gate Test Suite — Sections 46, 47, 48
Validates:
- AS-OF temporal joins
- Historical instrument universe tracking
- Zero look-ahead bias leakage gate
"""
from __future__ import annotations

import pytest
from app.ml.pit_store import PITStore
from app.ml.leakage_gate import LeakageGate, LeakageViolationError


def test_pit_as_of_temporal_join():
    """Verify that AS-OF join retrieves only information available by observation timestamp T."""
    store = PITStore()
    # Feature published at T=1000
    store.insert_record("NIFTY", "rsi", 45.0, observation_time_utc=1000, computed_at_utc=990, published_at_utc=1000)
    # Feature published at T=2000
    store.insert_record("NIFTY", "rsi", 65.0, observation_time_utc=2000, computed_at_utc=1990, published_at_utc=2000)

    # Query at T=1500 -> must return value from T=1000 (45.0), NOT T=2000 (65.0)
    joined_1500 = store.as_of_join("NIFTY", 1500)
    assert joined_1500["rsi"] == 45.0

    # Query at T=2500 -> returns latest (65.0)
    joined_2500 = store.as_of_join("NIFTY", 2500)
    assert joined_2500["rsi"] == 65.0


def test_pit_leakage_gate_detects_future_timestamps():
    """Verify LeakageGate blocks records where published_at > observation_time."""
    gate = LeakageGate()
    valid_dataset = [
        {
            "observation_time_utc": 1000,
            "publication_timestamps": {"rsi": 1000, "adx": 990},
        }
    ]
    passed, violations = gate.validate_features_matrix(valid_dataset)
    assert passed is True
    assert len(violations) == 0

    leaked_dataset = [
        {
            "observation_time_utc": 1000,
            "publication_timestamps": {"rsi": 1050},  # 50ms into the future!
        }
    ]
    passed, violations = gate.validate_features_matrix(leaked_dataset)
    assert passed is False
    assert len(violations) == 1

    with pytest.raises(LeakageViolationError):
        gate.assert_no_leakage(leaked_dataset)
