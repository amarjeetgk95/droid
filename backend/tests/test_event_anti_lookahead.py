import pytest
from datetime import datetime, timezone, date

from app.event_engine.models import CanonicalEvent, PredictionSnapshot
from app.event_engine.historical_matcher import historical_matcher


def test_anti_lookahead_strict_cutoff():
    """Spec §21: Historical evaluation must never use information that was unavailable
    at the prediction timestamp.
    """
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20241101",
        title="RBI MPC Test Cutoff",
        event_type="CENTRAL_BANK",
        sub_type="MONETARY_POLICY_RATE_DECISION",
        entity_id="RBI",
        event_timestamp=datetime(2024, 11, 1, 10, 0, tzinfo=timezone.utc),
    )

    # Cutoff set to 2024-11-01: events on 2024-12-06 and 2025-02-07 MUST NOT be visible!
    cutoff = datetime(2024, 11, 1, 0, 0, tzinfo=timezone.utc)
    matches = historical_matcher.match_comparables(event, data_cutoff=cutoff, top_k=10)

    for m in matches:
        match_date = date.fromisoformat(m.past_event_date)
        match_dt = datetime.combine(match_date, datetime.min.time(), tzinfo=timezone.utc)
        assert match_dt < cutoff, f"Leakage detected: past event {m.past_event_id} date {m.past_event_date} >= cutoff {cutoff}"


def test_prediction_snapshot_cutoff_fields():
    """Spec §20 & §21: Every prediction record must carry prediction_timestamp,
    data_cutoff_timestamp, feature_cutoff_timestamp, formula_version.
    """
    now = datetime(2026, 10, 9, 9, 30, tzinfo=timezone.utc)
    snapshot = PredictionSnapshot(
        canonical_event_id="RBI_MPC_20261009",
        prediction_timestamp=now,
        data_cutoff_timestamp=now,
        feature_cutoff_timestamp=now,
        formula_version="v3.0.0",
        configuration_version="v3.0.0",
        importance_score=92.5,
        market_impact_score=None,
        opportunity_score=None,
        decision="NO_TRADE",
        snapshot_immutable=True,
    )

    assert snapshot.prediction_timestamp == now
    assert snapshot.data_cutoff_timestamp == now
    assert snapshot.feature_cutoff_timestamp == now
    assert snapshot.snapshot_immutable is True
    assert snapshot.decision == "NO_TRADE"
