import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.event_engine.models import CanonicalEvent
from app.event_engine.signal_bridge import event_signal_bridge
from app.signals.fsm import SignalInstance


def test_event_signal_bridge_shadow_mode_attachment():
    """Spec §3 & §27: Event context attaches to signals and operates strictly in SHADOW_MODE."""
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI Monetary Policy Committee",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
        temporal_phase="ACTIVE",
    )

    ctx = event_signal_bridge.create_event_context(event, "BANKNIFTY")
    assert ctx.execution_mode == "SHADOW_MODE"
    assert ctx.event_id == "RBI_MPC_20261009"

    # Create dummy SignalInstance
    sig = SignalInstance(
        underlying="BANKNIFTY",
        strategy="Breakout",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("52000.0"),
        entry_min=Decimal("52010.0"),
        entry_max=Decimal("52040.0"),
        trigger=Decimal("52050.0"),
        stop_loss=Decimal("51900.0"),
        target_1=Decimal("52250.0"),
        target_2=Decimal("52450.0"),
        risk_points=Decimal("150.0"),
        risk_reward_t1=1.33,
        risk_reward_t2=2.67,
        confidence=82.0,
    )

    enriched = event_signal_bridge.enrich_signal(sig, event)
    assert "event_context" in enriched.confluence_breakdown
    assert enriched.confluence_breakdown["event_context"]["execution_mode"] == "SHADOW_MODE"

    # Record shadow execution
    shadow = event_signal_bridge.record_shadow_execution(
        signal_id=enriched.signal_id,
        event=event,
        underlying="BANKNIFTY",
        strategy="Breakout",
        direction="LONG_CALL",
        simulated_entry_price=52050.0,
    )
    assert shadow.execution_mode == "SHADOW_MODE"
    assert shadow.shadow_status == "TRACKING"
    assert shadow.simulated_entry_price == 52050.0
