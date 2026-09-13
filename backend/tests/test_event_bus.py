"""
Test Suite for Signal Event Bus & Decoupled Handlers (Phase 5)
"""
from __future__ import annotations

import asyncio
from decimal import Decimal
import pytest

from app.signals.event_bus import (
    SignalEvent,
    SignalEventType,
    SignalEventBus,
    signal_event_bus,
)
from app.signals.fsm import SignalFSMManager, SignalInstance


@pytest.mark.asyncio
async def test_event_bus_async_subscription_and_publish():
    bus = SignalEventBus()
    received = []

    async def async_handler(event: SignalEvent):
        received.append(event)

    bus.subscribe(SignalEventType.TRANSITIONED, async_handler)

    ev = SignalEvent(
        event_type=SignalEventType.TRANSITIONED,
        signal_id="SIG-TEST-001",
        payload={"to_state": "CONFIRMED"},
    )
    await bus.publish(ev)

    assert len(received) == 1
    assert received[0].signal_id == "SIG-TEST-001"
    assert received[0].payload["to_state"] == "CONFIRMED"


@pytest.mark.asyncio
async def test_event_bus_handler_failure_isolation():
    bus = SignalEventBus()
    received_healthy = []

    def broken_handler(event: SignalEvent):
        raise ValueError("Simulated handler crash")

    async def healthy_handler(event: SignalEvent):
        received_healthy.append(event.signal_id)

    bus.subscribe(SignalEventType.TRANSITIONED, broken_handler)
    bus.subscribe(SignalEventType.TRANSITIONED, healthy_handler)

    ev = SignalEvent(
        event_type=SignalEventType.TRANSITIONED,
        signal_id="SIG-FAIL-ISOLATION",
        payload={"to_state": "ARMED"},
    )
    await bus.publish(ev)

    # Healthy handler must have executed despite broken_handler failure
    assert received_healthy == ["SIG-FAIL-ISOLATION"]

    # Failure must be recorded in failure log
    log = bus.get_failure_log()
    assert len(log) == 1
    assert log[0]["signal_id"] == "SIG-FAIL-ISOLATION"
    assert "Simulated handler crash" in log[0]["error"]


def test_event_bus_publish_sync_without_loop():
    bus = SignalEventBus()
    received = []

    def sync_handler(event: SignalEvent):
        received.append(event.signal_id)

    bus.subscribe(SignalEventType.REGISTERED, sync_handler)

    ev = SignalEvent(
        event_type=SignalEventType.REGISTERED,
        signal_id="SIG-SYNC-TEST",
        payload={"underlying": "NIFTY"},
    )
    bus.publish_sync(ev)

    assert received == ["SIG-SYNC-TEST"]


@pytest.mark.asyncio
async def test_event_bus_publish_sync_with_running_loop():
    bus = SignalEventBus()
    received = []

    async def async_handler(event: SignalEvent):
        received.append(event.signal_id)

    bus.subscribe(SignalEventType.BREAKEVEN_ACTIVATED, async_handler)

    ev = SignalEvent(
        event_type=SignalEventType.BREAKEVEN_ACTIVATED,
        signal_id="SIG-LOOP-SYNC",
        payload={"new_sl": 25100.0},
    )
    bus.publish_sync(ev)

    # Yield to event loop to allow scheduled task to run
    await asyncio.sleep(0.01)

    assert received == ["SIG-LOOP-SYNC"]


@pytest.mark.asyncio
async def test_fsm_emits_event_on_transition():
    fsm = SignalFSMManager()
    events_received = []

    async def on_transition(event: SignalEvent):
        if event.signal_id == "SIG-FSM-EVENT-TEST":
            events_received.append(event)

    signal_event_bus.subscribe(SignalEventType.TRANSITIONED, on_transition)

    try:
        sig = SignalInstance(
            signal_id="SIG-FSM-EVENT-TEST",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("25000.0"),
            entry_min=Decimal("25010.0"),
            entry_max=Decimal("25020.0"),
            trigger=Decimal("25015.0"),
            stop_loss=Decimal("24980.0"),
            target_1=Decimal("25050.0"),
            target_2=Decimal("25100.0"),
            risk_points=Decimal("35.0"),
            risk_reward_t1=1.5,
            risk_reward_t2=3.0,
            confidence=80.0,
            fsm_state="DETECTED",
        )
        fsm.register(sig)
        fsm.transition(sig.signal_id, "VALIDATED", market_price=Decimal("25010.0"))

        await asyncio.sleep(0.01)

        assert len(events_received) >= 1
        last_ev = events_received[-1]
        assert last_ev.signal_id == "SIG-FSM-EVENT-TEST"
        assert last_ev.payload["from_state"] == "DETECTED"
        assert last_ev.payload["to_state"] == "VALIDATED"
    finally:
        signal_event_bus.unsubscribe(SignalEventType.TRANSITIONED, on_transition)
