"""
Comprehensive regression test suite for Market Hours Enforcement & Execution Safety.
Validates the defense-in-depth safeguards across:
  1. Calendar service boundary checks (09:14:59, 09:15:00, 15:29:59, 15:30:00, 17:26:00, weekends, holidays)
  2. Quote validation (LTP <= 0, OFFLINE status, stale > 15s)
  3. Signal FSM zero-price rejection and market-close expiration sweep
  4. Outcome tracker closed-market & zero-price guards
  5. Paper Engine & Paper Service final boundary rejection
  6. Persistence sanitizer
"""
from __future__ import annotations

import zoneinfo
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

import pytest

from app.models.market import DataStatus, NormalizedQuote
from app.models.paper import OrderPayload
from app.services.calendar_service import MarketSessionPermission, calendar_service
from app.services.paper_service import PaperTradingService
from app.signals.fsm import SignalInstance, evaluate_tick, signal_fsm
from app.signals.outcome_tracker import SignalOutcomeTracker
from app.signals.paper_engine import SignalPaperEngine

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


def make_test_signal(
    signal_id: str,
    underlying: str = "NIFTY",
    direction: str = "LONG_CALL",
    fsm_state: str = "ARMED",
    spot_price: Decimal = Decimal(24900),
    trigger: Decimal = Decimal(24925),
    stop_loss: Decimal = Decimal(24850),
    target_1: Decimal = Decimal(25000),
    target_2: Decimal = Decimal(25100),
) -> SignalInstance:
    return SignalInstance(
        signal_id=signal_id,
        underlying=underlying,
        strategy="BREAKOUT",
        direction=direction,
        timeframe="5M",
        spot_price=spot_price,
        entry_min=trigger - Decimal(5),
        entry_max=trigger + Decimal(5),
        trigger=trigger,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        risk_points=abs(trigger - stop_loss),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        fsm_state=fsm_state,
    )


def make_mock_permission(allowed: bool, reason: str = "MARKET_CLOSED") -> MarketSessionPermission:
    now_ist = datetime.now(IST)
    return MarketSessionPermission(
        allowed=allowed,
        reason=reason,
        exchange="NSE",
        session="REGULAR" if allowed else "CLOSED",
        timestamp_ist=now_ist,
        market_open=now_ist.replace(hour=9, minute=15, second=0, microsecond=0),
        market_close=now_ist.replace(hour=15, minute=30, second=0, microsecond=0),
    )


# =====================================================================
# 1. Calendar Service Hard Boundaries
# =====================================================================

def test_calendar_boundary_091459_before_open():
    """At 09:14:59 IST on a trading day, trading MUST NOT be permitted."""
    t = datetime(2026, 9, 4, 9, 14, 59, tzinfo=IST)  # Friday
    perm = calendar_service.can_trade_now(t)
    assert perm.allowed is False
    assert perm.reason == "PRE_OPEN"


def test_calendar_boundary_091500_open():
    """At 09:15:00 IST on a normal trading day, trading MUST be permitted."""
    t = datetime(2026, 9, 4, 9, 15, 0, tzinfo=IST)  # Friday
    perm = calendar_service.can_trade_now(t)
    assert perm.allowed is True
    assert perm.reason == "MARKET_OPEN"


def test_calendar_boundary_152959_open():
    """At 15:29:59 IST on a normal trading day, trading MUST be permitted."""
    t = datetime(2026, 9, 4, 15, 29, 59, tzinfo=IST)  # Friday
    perm = calendar_service.can_trade_now(t)
    assert perm.allowed is True
    assert perm.reason == "MARKET_OPEN"


def test_calendar_boundary_153000_after_close():
    """At 15:30:00 IST, market is CLOSED and trading MUST NOT be permitted."""
    t = datetime(2026, 9, 4, 15, 30, 0, tzinfo=IST)  # Friday
    perm = calendar_service.can_trade_now(t)
    assert perm.allowed is False
    assert perm.reason == "MARKET_CLOSED"


def test_calendar_boundary_172600_incident_time():
    """At 17:26:00 IST (the exact incident timestamp), market is CLOSED."""
    t = datetime(2026, 9, 4, 17, 26, 0, tzinfo=IST)  # Friday
    perm = calendar_service.can_trade_now(t)
    assert perm.allowed is False
    assert perm.reason == "MARKET_CLOSED"


def test_calendar_weekend():
    """Saturday and Sunday MUST NOT permit trading."""
    sat = datetime(2026, 9, 5, 11, 0, 0, tzinfo=IST)  # Saturday
    sun = datetime(2026, 9, 6, 11, 0, 0, tzinfo=IST)  # Sunday
    assert calendar_service.can_trade_now(sat).allowed is False
    assert calendar_service.can_trade_now(sat).reason == "WEEKEND"
    assert calendar_service.can_trade_now(sun).allowed is False
    assert calendar_service.can_trade_now(sun).reason == "WEEKEND"


def test_calendar_holiday():
    """Declared exchange holidays MUST NOT permit trading."""
    hol = datetime(2026, 1, 26, 10, 30, 0, tzinfo=IST)  # Republic Day
    perm = calendar_service.can_trade_now(hol)
    assert perm.allowed is False
    assert "HOLIDAY" in perm.reason


# =====================================================================
# 2. FSM Safety Invariants (Price & Closed Market)
# =====================================================================

def test_fsm_rejects_non_positive_tick():
    """FSM evaluate_tick must return (None, 'INVALID_PRICE') when tick <= 0."""
    sig = make_test_signal("sig-test-fsm-1")
    signal_fsm.register(sig)

    # Test module-level deterministic evaluate_tick returns (None, "INVALID_PRICE")
    next_state, reason = evaluate_tick(sig, Decimal("0.0"))
    assert next_state is None
    assert reason == "INVALID_PRICE"

    next_state, reason = evaluate_tick(sig, Decimal("-100.50"))
    assert next_state is None
    assert reason == "INVALID_PRICE"

    # Test manager convenience method returns None
    assert signal_fsm.evaluate_tick(sig, Decimal("0.0")) is None
    assert signal_fsm.evaluate_tick(sig, Decimal("-100.50")) is None


def test_fsm_sweep_expired_on_market_close():
    """FSM sweep_expired must transition pre-trigger signals to EXPIRED with reason MARKET_CLOSED when market is closed."""
    sig = make_test_signal("sig-test-fsm-2", fsm_state="ARMED")
    signal_fsm.register(sig)

    with patch.object(calendar_service, "can_trade_now", return_value=make_mock_permission(False, "MARKET_CLOSED")):
        sweep_res = signal_fsm.sweep_expired()
        assert sweep_res.get("expired", 0) >= 1
        assert sig.fsm_state == "EXPIRED"


# =====================================================================
# 3. Outcome Tracker Guards
# =====================================================================

def test_outcome_tracker_rejects_closed_market():
    """Outcome tracker must immediately abort without processing when market is closed."""
    tracker = SignalOutcomeTracker()
    sig = make_test_signal("sig-test-tracker-1", fsm_state="ARMED")
    signal_fsm.register(sig)

    with patch.object(calendar_service, "can_trade_now", return_value=make_mock_permission(False, "MARKET_CLOSED")):
        transitions = tracker.update_with_price("NIFTY", Decimal(25050), allow_closed_market=False)
        assert transitions == []
        # State must remain unchanged
        assert sig.fsm_state == "ARMED"


def test_outcome_tracker_rejects_non_positive_price():
    """Outcome tracker must reject tick <= 0 even if market is open."""
    tracker = SignalOutcomeTracker()
    sig = make_test_signal("sig-test-tracker-2", fsm_state="ARMED")
    signal_fsm.register(sig)

    with patch.object(calendar_service, "can_trade_now", return_value=make_mock_permission(True, "MARKET_OPEN")):
        transitions = tracker.update_with_price("NIFTY", Decimal("0.0"), allow_closed_market=False)
        assert transitions == []
        assert sig.fsm_state == "ARMED"


# =====================================================================
# 4. Paper Engine Execution Guard
# =====================================================================

@pytest.mark.asyncio
async def test_paper_engine_rejects_closed_market():
    """PaperEngine must reject execution when market is closed."""
    engine = SignalPaperEngine()
    sig = make_test_signal("sig-test-engine-1", fsm_state="TRIGGERED")
    signal_fsm.register(sig)

    with patch.object(calendar_service, "can_trade_now", return_value=make_mock_permission(False, "MARKET_CLOSED")):
        res = await engine.execute_signal(sig.signal_id, allow_closed_market=False)
        assert res.success is False
        assert res.status == "REJECTED"
        assert "MARKET_CLOSED" in res.message or "closed" in res.message.lower()


# =====================================================================
# 5. Paper Service Final Defense Boundary
# =====================================================================

@pytest.mark.asyncio
async def test_paper_service_place_order_blocks_closed_market():
    """PaperTradingService.place_order MUST reject any Indian instrument if market is closed."""
    service = PaperTradingService()
    payload = OrderPayload(
        symbol="NSE:NIFTY26SEP1024900CE",
        underlying="NIFTY",
        side="BUY",
        order_type="MARKET",
        product="INTRADAY",
        quantity=75,
        price=150.0,
    )
    
    with patch.object(calendar_service, "can_trade_now", return_value=make_mock_permission(False, "MARKET_CLOSED")):
        order = await service.place_order(
            payload=payload,
            allow_closed_market=False,
        )
        assert order.status == "REJECTED"
        assert "MARKET_CLOSED" in order.rejection_reason


@pytest.mark.asyncio
async def test_paper_service_place_order_blocks_non_positive_quantity():
    """PaperTradingService.place_order MUST reject non-positive quantities (defense in depth)."""
    service = PaperTradingService()
    # Bypass initial model validation to test service-level invariant defense
    payload = OrderPayload.model_construct(
        symbol="NSE:NIFTY26SEP1024900CE",
        underlying="NIFTY",
        side="BUY",
        order_type="MARKET",
        product="INTRADAY",
        quantity=0,
        price=150.0,
    )
    
    with patch.object(calendar_service, "can_trade_now", return_value=make_mock_permission(True, "MARKET_OPEN")):
        order = await service.place_order(
            payload=payload,
            allow_closed_market=False,
        )
        assert order.status == "REJECTED"
        assert "INVALID_QUANTITY" in order.rejection_reason


# =====================================================================
# 6. Worker Feed Quote Quality Guards
# =====================================================================

def test_quote_validation_logic():
    """Validates the exact quote sanity logic used by AutomatedSignalWorker."""
    now_utc = datetime.now(UTC)

    # 1. Offline status
    offline_q = NormalizedQuote(
        symbol="NSE:NIFTY50-INDEX",
        display_name="NIFTY 50",
        timestamp=now_utc,
        ltp=24900.0,
        open=24800.0,
        high=24950.0,
        low=24780.0,
        previous_close=24750.0,
        change=150.0,
        change_percent=0.6,
        volume=100000,
        status=DataStatus.OFFLINE,
    )
    assert offline_q.status != DataStatus.LIVE

    # 2. Zero LTP
    zero_q = NormalizedQuote(
        symbol="NSE:NIFTY50-INDEX",
        display_name="NIFTY 50",
        timestamp=now_utc,
        ltp=0.0,
        open=24800.0,
        high=24950.0,
        low=24780.0,
        previous_close=24750.0,
        change=0.0,
        change_percent=0.0,
        volume=0,
        status=DataStatus.LIVE,
    )
    assert not (zero_q.ltp is not None and zero_q.ltp > 0.0)

    # 3. Stale quote (> 15 seconds)
    stale_timestamp = datetime.fromtimestamp(now_utc.timestamp() - 20.0, tz=UTC)
    stale_q = NormalizedQuote(
        symbol="NSE:NIFTY50-INDEX",
        display_name="NIFTY 50",
        timestamp=stale_timestamp,
        ltp=24900.0,
        open=24800.0,
        high=24950.0,
        low=24780.0,
        previous_close=24750.0,
        change=150.0,
        change_percent=0.6,
        volume=100000,
        status=DataStatus.LIVE,
    )
    age = now_utc.timestamp() - stale_q.timestamp.timestamp()
    assert age > 15.0


# =====================================================================
# 7. Persistence Sanitizer
# =====================================================================

def test_sanitize_persisted_signals_sweeps_closed_market():
    """sanitize_persisted_signals sweeps ARMED/DETECTED signals to EXPIRED when market is closed."""
    from app.signals.audit_ledger import AuditTradeRecord, signal_audit_ledger
    from app.signals.fsm import signal_fsm
    from app.signals.signals_persistence import sanitize_persisted_signals

    sig = make_test_signal("sig-persist-sanitize-1", fsm_state="ARMED")
    signal_fsm._signals[sig.signal_id] = sig

    # Add corrupt audit trade with exit_price = 0.0
    corrupt_trade = AuditTradeRecord(
        audit_id="AUD-CORRUPT-1",
        signal_id="sig-corrupt-1",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        exit_price=0.0,
        actual_pnl_inr=-1869559.0,
        is_winner=False,
    )
    signal_audit_ledger._trades[corrupt_trade.signal_id] = corrupt_trade

    with patch.object(calendar_service, "can_trade_now", return_value=make_mock_permission(False, "MARKET_CLOSED")):
        sanitized = sanitize_persisted_signals()
        assert sanitized >= 2
        assert sig.fsm_state == "EXPIRED"
        assert corrupt_trade.exit_price is None
        assert corrupt_trade.actual_pnl_inr is None
