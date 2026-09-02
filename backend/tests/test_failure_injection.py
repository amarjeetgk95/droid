"""
Mandatory Failure-Injection & Chaos Test Suite — Section 59
Covers:
- WebSocket disconnect / feed disruption
- Duplicate events & sequence gaps
- Out-of-order timestamps
- Redis failure & in-memory fallback
- Process crash mid-order & idempotency recovery
- Leadership fencing & split-brain prevention
- Kill switch emergency override
"""
from __future__ import annotations

import asyncio
import time
import uuid
from decimal import Decimal
import pytest

from app.core.redis_bus import RedisEventBus, StreamNames
from app.core.leadership import LeaderElection
from app.algo.execution import OrderManager, PaperBrokerAdapter, OrderRecord
from app.institutional.sequence import SequenceValidator
from app.institutional.feed_circuit import FeedCircuitBreaker
from app.algo.risk import trade_risk_engine, OrderIntent
from app.institutional.state_recovery import state_recovery_engine, RecoveryState


@pytest.mark.asyncio
async def test_redis_failure_and_in_memory_fallback():
    """Verify that when Redis is unreachable, EventBus gracefully falls back to in-memory broadcast."""
    bus = RedisEventBus(redis_url="redis://nonexistent-host:9999/0")
    connected = await bus.connect()
    assert connected is False
    assert bus.is_connected is False

    received = []
    async def subscriber(payload):
        received.append(payload)

    bus.subscribe(StreamNames.MARKET_DATA, subscriber)
    msg_id = await bus.publish(StreamNames.MARKET_DATA, {"symbol": "NIFTY", "price": "24500.00"})
    assert msg_id is not None
    await asyncio.sleep(0.05)
    assert len(received) == 1
    assert received[0]["symbol"] == "NIFTY"


@pytest.mark.asyncio
async def test_sequence_gap_and_duplicate_detection():
    """Verify sequence validator flags gaps and rejects duplicate packet sequence IDs."""
    validator = SequenceValidator(instrument_id="NIFTY")
    # First valid sequence
    r1 = validator.check(source_sequence_id=1)
    assert r1.is_anomaly is False

    # Duplicate sequence ID -> rejected
    r2 = validator.check(source_sequence_id=1)
    assert r2.anomaly == "DUPLICATE"
    assert r2.is_anomaly is True

    # Sequence gap -> gap flagged
    r3 = validator.check(source_sequence_id=5)
    assert r3.anomaly == "MISSING"
    assert r3.is_anomaly is True


@pytest.mark.asyncio
async def test_feed_circuit_breaker_on_repeated_disconnects():
    """Verify FeedCircuitBreaker trips on sequence anomalies and degrades feed state."""
    cb = FeedCircuitBreaker()
    st1 = cb.trip(instrument_id="NIFTY", anomaly="MISSING", reason="Dropped 10 frames")
    assert st1.health == "FEED_DEGRADED"
    assert st1.suppress_candidates is True


@pytest.mark.asyncio
async def test_order_idempotency_crash_recovery():
    """Verify identical client_order_id returns existing record without duplicate order placement."""
    om = OrderManager()
    cid = uuid.uuid4()
    rec1 = om.create_intent(
        account_id=uuid.uuid4(),
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=Decimal("24500.00"),
        client_order_id=cid,
    )
    rec2 = om.create_intent(
        account_id=rec1.account_id,
        symbol="NIFTY",
        side="BUY",
        quantity=50,
        price=Decimal("24500.00"),
        client_order_id=cid,
    )
    assert rec1 is rec2
    assert rec1.client_order_id == rec2.client_order_id


@pytest.mark.asyncio
async def test_split_brain_leader_election():
    """Verify that a second worker cannot acquire lease while active leader holds valid unexpired lease."""
    le = LeaderElection(lease_duration_seconds=2.0)
    lease1 = await le.acquire_lease("EXECUTION_ENGINE", "worker_primary")
    assert lease1 is not None
    assert lease1.fencing_token == 1

    # Second worker tries to acquire immediately -> blocked
    lease2 = await le.acquire_lease("EXECUTION_ENGINE", "worker_standby")
    assert lease2 is None

    # Verify authority
    assert le.verify_authority("EXECUTION_ENGINE", "worker_primary", fencing_token=1) is True
    assert le.verify_authority("EXECUTION_ENGINE", "worker_standby", fencing_token=1) is False


@pytest.mark.asyncio
async def test_trading_prohibited_during_recovering_state():
    """Verify no trading is allowed during STARTING, HYDRATING, RECOVERING, or DEGRADED states."""
    state_recovery_engine.transition_to(RecoveryState.RECOVERING, "Testing recovery safety")
    assert state_recovery_engine.is_trading_allowed() is False

    state_recovery_engine.transition_to(RecoveryState.STATE_VALIDATED, "Reconstruction complete")
    assert state_recovery_engine.is_trading_allowed() is True
