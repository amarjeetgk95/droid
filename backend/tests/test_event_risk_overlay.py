import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal

from app.event_engine.models import CanonicalEvent
from app.event_engine.risk_overlay import event_risk_overlay_service
from app.signals.risk_engine import central_risk_engine, StrategySetup


def test_event_risk_overlay_normal_proximity():
    """When event is more than 30 minutes away, overlay returns NORMAL proximity with 1.0x sizing."""
    now = datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc)
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI MPC Decision",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
    )

    overlay = event_risk_overlay_service.evaluate_overlay("BANKNIFTY", [event], now=now)
    assert overlay.proximity_state == "NORMAL"
    assert overlay.can_enter is True
    assert overlay.sizing_multiplier == 1.0


def test_event_risk_overlay_approaching_window():
    """Between T-30m and T-5m, sizing multiplier is dampened to 0.5x."""
    now = datetime(2026, 10, 9, 9, 45, tzinfo=timezone.utc)  # 15 minutes before 10:00
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI MPC Decision",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
    )

    overlay = event_risk_overlay_service.evaluate_overlay("BANKNIFTY", [event], now=now)
    assert overlay.proximity_state == "APPROACHING_WINDOW"
    assert overlay.can_enter is True
    assert overlay.sizing_multiplier == 0.5
    assert overlay.prohibit_naked_options is True


def test_event_risk_overlay_blackout_window():
    """Between T-5m and T+5m, trades are strictly forbidden with can_enter=False."""
    now = datetime(2026, 10, 9, 9, 58, tzinfo=timezone.utc)  # 2 minutes before 10:00
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI MPC Decision",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
    )

    overlay = event_risk_overlay_service.evaluate_overlay("BANKNIFTY", [event], now=now)
    assert overlay.proximity_state == "BLACKOUT_WINDOW"
    assert overlay.can_enter is False
    assert overlay.sizing_multiplier == 0.0
    assert "EVENT_BLACKOUT_ACTIVE" in (overlay.rejection_reason or "")


def test_central_risk_engine_integration_with_event_overlay():
    """CentralRiskEngine rejects trades during blackout window and dampens sizing during approaching window."""
    now = datetime(2026, 10, 9, 9, 58, tzinfo=timezone.utc)
    event = CanonicalEvent(
        canonical_event_id="RBI_MPC_20261009",
        title="RBI MPC Decision",
        event_type="CENTRAL_BANK",
        entity_id="RBI",
        event_timestamp=datetime(2026, 10, 9, 10, 0, tzinfo=timezone.utc),
    )

    setup = StrategySetup(
        strategy_name="EMA_PULLBACK",
        underlying="BANKNIFTY",
        direction="LONG_CALL",
        spot_price=Decimal("51000.0"),
        entry_trigger=Decimal("51000.0"),
        raw_structural_stop=Decimal("50940.0"),  # 60 pts risk
        confidence=85.0,
    )

    decision = central_risk_engine.evaluate_with_events(
        setup=setup,
        events=[event],
        available_capital=200000.0,
        risk_per_trade_pct=1.0,
        allow_closed_market=True,
        now=now,
    )

    assert decision.accepted is False
    assert "EVENT_RISK_REJECTED" in (decision.rejection_reason or "")
