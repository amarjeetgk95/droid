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
async def test_fsm_emits_event_on_transition(monkeypatch):
    """The FSM must publish a TRANSITIONED event for each accepted transition.

    `publish_sync` schedules the dispatch as a task on the running loop, and the
    global bus also carries the app's own TRANSITIONED handlers (audit ledger,
    persistence, Telegram, SSE), some of which touch the DB/network. Racing that
    chain against a fixed `asyncio.sleep(0.01)` made this test depend on handler
    speed and on what other tests had imported. Capture the publish call
    instead: this asserts the FSM's emission contract directly and
    deterministically.
    """
    fsm = SignalFSMManager()
    published: list[SignalEvent] = []

    monkeypatch.setattr(signal_event_bus, "publish_sync", published.append, raising=True)

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

    transitions = [
        ev
        for ev in published
        if ev.event_type == SignalEventType.TRANSITIONED
        and ev.signal_id == "SIG-FSM-EVENT-TEST"
    ]
    assert len(transitions) == 1
    last_ev = transitions[-1]
    assert last_ev.payload["from_state"] == "DETECTED"
    assert last_ev.payload["to_state"] == "VALIDATED"
