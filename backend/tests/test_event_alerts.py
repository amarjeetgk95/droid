import pytest
from app.event_engine.alert_service import event_alert_service


def test_event_alert_emission_and_cooldown_deduplication():
    """Spec §29: Alerts must be generated from state transitions and deduplicated with cooldowns."""
    canonical_id = "RBI_MPC_20261009"

    # First emission: should succeed
    alert1 = event_alert_service.emit_alert(
        canonical_event_id=canonical_id,
        alert_type="EVENT_APPROACHING",
        title="RBI MPC Approaching",
        message="Scheduled for 10:00 AM IST",
        state_fingerprint="APPROACHING_T4H",
    )
    assert alert1 is not None
    assert alert1.status == "PENDING_REVIEW"

    # Immediate second emission with identical signature: MUST be suppressed by cooldown
    alert2 = event_alert_service.emit_alert(
        canonical_event_id=canonical_id,
        alert_type="EVENT_APPROACHING",
        title="RBI MPC Approaching",
        message="Duplicate message on monitoring tick",
        state_fingerprint="APPROACHING_T4H",
    )
    assert alert2 is None, "Cooldown failed: duplicate alert was not suppressed"

    # State transition to new state: should succeed
    alert3 = event_alert_service.emit_alert(
        canonical_event_id=canonical_id,
        alert_type="OPPORTUNITY_CONFIRMED",
        title="Opportunity Confirmed",
        message="Setup active in SHADOW_MODE",
        state_fingerprint="SHADOW_ACTIVE",
    )
    assert alert3 is not None
    assert alert3.alert_type == "OPPORTUNITY_CONFIRMED"

    # Acknowledgment
    ack = event_alert_service.acknowledge_alert(alert1.alert_id, user_name="TRADER_1")
    assert ack is not None
    assert ack.status == "ACKNOWLEDGED"
    assert ack.acknowledged_by == "TRADER_1"
