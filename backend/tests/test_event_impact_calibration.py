import pytest
from datetime import datetime, timezone

from app.event_engine.models import CanonicalEvent
from app.event_engine.impact_calibrator import market_impact_calibration_service
from app.event_engine.scoring_service import scoring_service


def test_market_impact_calibration_service():
    """Empirical calibration transitions Market Impact to SCORED with empirical percentiles."""
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI Monetary Policy Committee Rate Decision",
        event_type="CENTRAL_BANK",
        sub_type="MONETARY_POLICY_RATE_DECISION",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
    )

    impact = market_impact_calibration_service.calibrate_market_impact(
        event=event,
        current_iv=16.5,
    )

    assert impact.status == "SCORED"
    assert impact.final_score is not None
    assert impact.final_score > 50.0
    assert impact.historical_move_percentile is not None
    assert impact.volatility_regime is not None
    assert "Calibrated against N=" in (impact.reason or "")


def test_scoring_service_use_calibration_flag():
    """Scoring service respects use_calibration flag."""
    event = CanonicalEvent(
        canonical_event_id="NSE_CORP_INFY_20261015",
        title="Infosys Q2 Results",
        event_type="EARNINGS",
        entity_id="INFY",
        event_timestamp=datetime(2026, 10, 15, 16, 0, tzinfo=timezone.utc),
    )

    # 1. Uncalibrated returns INSUFFICIENT_DATA
    uncalibrated = scoring_service.calculate_market_impact_score(event, use_calibration=False)
    assert uncalibrated.status == "INSUFFICIENT_DATA"
    assert uncalibrated.final_score is None

    # 2. Calibrated returns SCORED
    calibrated = scoring_service.calculate_market_impact_score(event, use_calibration=True)
    assert calibrated.status == "SCORED"
    assert calibrated.final_score is not None
