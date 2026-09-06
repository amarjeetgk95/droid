import pytest
from datetime import datetime, timezone, timedelta

from app.event_engine.scheduler import EventIngestionScheduler


def test_scheduler_health_and_circuit_breaker():
    """Validates source health tracking, circuit breaker tripping on errors, and cooldown."""
    sched = EventIngestionScheduler(error_threshold_to_trip=3, cooldown_minutes=5.0)

    # 1. Successful fetch records HEALTHY status
    sched.record_success("RBI_OFFICIAL", latency_ms=45.2)
    telemetry = sched.get_telemetry()
    rbi_rec = telemetry.sources["RBI_OFFICIAL"]
    assert rbi_rec.status == "HEALTHY"
    assert rbi_rec.circuit_state == "CLOSED"
    assert rbi_rec.last_latency_ms == 45.2
    assert rbi_rec.success_count == 1

    # 2. Consecutive errors trip circuit breaker
    now = datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc)
    sched.record_failure("NSE_CORPORATE", "Connection timeout", now=now)
    assert sched.can_attempt_sync("NSE_CORPORATE", now=now)[0] is True  # 1 error, not tripped

    sched.record_failure("NSE_CORPORATE", "HTTP 502", now=now)
    sched.record_failure("NSE_CORPORATE", "HTTP 503", now=now)

    # Now tripped
    nse_rec = sched.get_telemetry().sources["NSE_CORPORATE"]
    assert nse_rec.status == "OFFLINE"
    assert nse_rec.circuit_state == "OPEN"
    assert "NSE_CORPORATE" in sched.get_telemetry().active_circuit_breakers

    # During cooldown, sync is blocked
    can_sync, reason = sched.can_attempt_sync("NSE_CORPORATE", now=now + timedelta(minutes=2))
    assert can_sync is False
    assert "CIRCUIT_OPEN" in reason

    # After cooldown, transitions to HALF_OPEN probe
    can_probe, probe_reason = sched.can_attempt_sync("NSE_CORPORATE", now=now + timedelta(minutes=6))
    assert can_probe is True
    assert "HALF_OPEN" in probe_reason
