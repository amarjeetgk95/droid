import pytest
from datetime import datetime, timezone

from app.event_engine.models import CanonicalEvent
from app.event_engine.outcome_recorder import EventOutcome
from app.event_engine.signal_bridge import ShadowSignalRecord
from app.event_engine.validation_service import event_validation_service


def test_event_validation_service_track_record():
    """Validates directional accuracy, win-rate, MFE/MAE aggregation and sample size gate."""
    # Create sample settled outcomes
    outcomes = [
        EventOutcome(
            canonical_event_id="EV-1",
            measured_at=datetime.now(timezone.utc),
            predicted_direction="BULLISH",
            actual_direction="BULLISH",
            prediction_correct=True,
            initial_move_pct=0.45,
            maximum_move_pct=1.35,
            mfe_pct=1.35,
            mae_pct=0.15,
            iv_change_pct=-18.5,
            is_settled=True,
        ),
        EventOutcome(
            canonical_event_id="EV-2",
            measured_at=datetime.now(timezone.utc),
            predicted_direction="BEARISH",
            actual_direction="BULLISH",
            prediction_correct=False,
            initial_move_pct=-0.20,
            maximum_move_pct=0.85,
            mfe_pct=0.20,
            mae_pct=0.85,
            iv_change_pct=-14.0,
            is_settled=True,
        ),
    ]

    # Create sample shadow signals
    shadows = [
        ShadowSignalRecord(
            canonical_event_id="EV-1",
            base_signal_id="SIG-1",
            underlying="BANKNIFTY",
            strategy="EVENT_MOMENTUM",
            direction="LONG_CALL",
            event_importance_score=85.0,
            event_opportunity_score=80.0,
            suggested_sizing_factor=1.0,
            simulated_pnl_pct=2.4,
            shadow_status="COMPLETED",
        ),
        ShadowSignalRecord(
            canonical_event_id="EV-2",
            base_signal_id="SIG-2",
            underlying="BANKNIFTY",
            strategy="EVENT_MOMENTUM",
            direction="LONG_PUT",
            event_importance_score=85.0,
            event_opportunity_score=78.0,
            suggested_sizing_factor=1.0,
            simulated_pnl_pct=-0.9,
            shadow_status="COMPLETED",
        ),
    ]

    record = event_validation_service.compute_track_record(
        outcomes=outcomes,
        shadow_records=shadows,
    )

    assert record.total_events_evaluated == 2
    assert record.settled_events_count == 2
    assert record.shadow_trades_count == 2
    assert record.directional_accuracy_pct == 50.0
    assert record.shadow_win_rate_pct == 50.0
    assert record.profit_factor > 1.5
    assert record.average_mfe_pct > 0.0
    assert record.average_mae_pct > 0.0
    assert record.sample_size_gate_passed is False  # N=2 < 30
    assert record.recommendation == "ACCUMULATE_MORE_EVENTS"
