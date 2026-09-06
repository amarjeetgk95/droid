import pytest
from datetime import datetime, timezone, timedelta
from app.event_engine.models import CanonicalEvent
from app.event_engine.outcome_recorder import event_outcome_recorder


def test_post_event_outcome_reaction_calculation():
    """Spec §24: Measure actual move, MFE, MAE, IV crush, and keep PREDICTION & OUTCOME separate."""
    now = datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc)
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI Monetary Policy Committee",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=now,
        expected_direction="BULLISH",
    )

    baseline = 52000.0
    # Price sequence: initial bump, peak, slight pullback
    prices = [
        ("T+1M", now + timedelta(minutes=1), 52120.0),
        ("T+5M", now + timedelta(minutes=5), 52350.0),
        ("T+15M", now + timedelta(minutes=15), 52500.0),
        ("T+30M", now + timedelta(minutes=30), 52420.0),
    ]

    outcome = event_outcome_recorder.calculate_reaction(
        event=event,
        primary_instrument="BANKNIFTY",
        baseline_price=baseline,
        price_progression=prices,
        pre_iv=18.5,
        post_iv=14.2,  # IV crush!
        pre_oi=1200000,
        post_oi=1350000,
    )

    assert outcome.canonical_event_id == event.canonical_event_id
    assert outcome.predicted_direction == "BULLISH"
    assert outcome.actual_direction == "BULLISH"
    assert outcome.prediction_correct is True
    assert outcome.initial_move_pct > 0.2
    assert outcome.maximum_move_pct > 0.9
    assert outcome.mfe_pct > 0.9
    assert outcome.iv_change_pct is not None
    assert outcome.iv_change_pct < -20.0  # -23.24% IV crush
    assert outcome.is_settled is True
