"""
Regression tests: ghost-open settlement gaps in the Signal Centre.

Covers three related defects:

1. Runner TTL pre-emption: list_active() -> sweep_expired() force-transitions a
   TARGET_1_HIT runner (or a CONFIRMED trade on time-stop) to a terminal state
   BEFORE evaluate_tick ever sees the tick; the outcome tracker then skipped
   terminal states entirely, so the runner's residual quantity was never
   squared off in the paper portfolio and the audit row stayed EXECUTED with
   frozen MTM (ghost open position).
2. EOD square-off filter: the worker's _settle_eod_positions() only looked at
   CONFIRMED / TARGET_1_HIT signals, so runners the sweep had already converted
   to RUNNER_TIME_STOP_HIT moments earlier on the same market-close edge were
   invisible to the settle pass.
3. DB restore settleability: restore_signals_from_db() rebuilt SignalInstance
   without a paper_order, and close_signal_position() refuses signals without
   one — restored open positions could never be squared off.
"""
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest

from app.services.calendar_service import calendar_service, MarketSessionPermission
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.fill_reconciler import option_fill_reconciler
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.outcome_tracker import outcome_tracker
from app.signals.paper_engine import signal_paper_engine


OPTION_CONTRACT = {
    "broker_symbol": "NSE:NIFTY26SEP24900CE",
    "strike": 24900,
    "option_type": "CE",
    "lot_size": 75,
}


def make_perm(allowed: bool, reason: str = "TEST") -> MarketSessionPermission:
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    return MarketSessionPermission(
        allowed=allowed,
        reason=reason,
        exchange="NSE",
        session="REGULAR" if allowed else "CLOSED",
        timestamp_ist=now_ist,
        market_open=now_ist.replace(hour=9, minute=15),
        market_close=now_ist.replace(hour=15, minute=30),
    )


def make_runner_signal(signal_id: str) -> SignalInstance:
    """2-lot runner: T1 booked one lot (75), one lot (75) still open."""
    now_ms = int(time.time() * 1000)
    return SignalInstance(
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800.0"),
        entry_min=Decimal("24850.0"),
        entry_max=Decimal("24860.0"),
        trigger=Decimal("24855.0"),
        stop_loss=Decimal("24780.0"),
        target_1=Decimal("24930.0"),
        target_2=Decimal("25000.0"),
        risk_points=Decimal("75.0"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        option_contract=OPTION_CONTRACT,
        fsm_state="TARGET_1_HIT",
        t1_hit=True,
        t1_fill_timestamp=now_ms - 400_000,  # T1 > 5 minutes ago
        runner_time_stop_at_utc=now_ms - 1_000,  # runner TTL already elapsed
        intended_qty=Decimal("150"),
        remaining_qty=Decimal("75"),
        actual_fill_price=Decimal("120.0"),
        entry_price=Decimal("120.0"),
        paper_order={
            "symbol": OPTION_CONTRACT["broker_symbol"],
            "quantity": 150,
            "lots": 2,
            "order_id": "ORD-TEST-900",
            "status": "FILLED",
            "side": "BUY",
            "fill_price": 120.0,
        },
    )


def seed_audit_records(signal_id: str) -> None:
    signal_audit_ledger.record_signal_created(
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=24800.0,
        trigger=24855.0,
        stop_loss=24780.0,
        target_1=24930.0,
        target_2=25000.0,
        confidence=85.0,
        option_contract=OPTION_CONTRACT,
        lots=2,
        status="ARMED",
    )
    signal_audit_ledger.record_paper_executed(
        signal_id=signal_id,
        paper_order_id="ORD-TEST-900",
        fill_price=120.0,
        quantity=150,
        lots=2,
        side="BUY",
        margin_used=120.0 * 150,
    )


def seed_reconciliation(sig: SignalInstance) -> None:
    """Mirror the production flow: entry registered at CONFIRMED, T1 booked 50%."""
    option_fill_reconciler.reconcile_entry(sig, 120.0, 150, 75)
    option_fill_reconciler.reconcile_t1_exit(sig, 150.0, int(time.time() * 1000))


@pytest.fixture(autouse=True)
def clean_state():
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()
    option_fill_reconciler._records.clear()
    yield
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()
    option_fill_reconciler._records.clear()

@pytest.mark.asyncio
async def test_sweep_preempted_runner_still_settles_paper_and_audit():
    """Runner TTL elapsed: the sweep converts the runner to RUNNER_TIME_STOP_HIT
    before evaluate_tick runs. The reconciled exit (paper close + audit P&L)
    must still be executed for the residual quantity."""
    sig = make_runner_signal("SIG-RUNNER-PREEMPT-1")
    signal_fsm._signals[sig.signal_id] = sig
    seed_audit_records(sig.signal_id)
    seed_reconciliation(sig)

    with patch.object(calendar_service, "can_trade_now", return_value=make_perm(True)):
        with patch.object(signal_paper_engine, "close_signal_position", new_callable=AsyncMock) as mock_close:
            await outcome_tracker.process_price_update_async("NIFTY", Decimal("24940.0"))

    # Paper position squared off with the pre-empted exit reason
    assert mock_close.await_count == 1
    assert mock_close.await_args.kwargs["reason"] == "RUNNER_TIME_STOP_HIT"

    # Reconciler booked the residual quantity and closed the record
    rec = option_fill_reconciler.get_reconciliation(sig.signal_id)
    assert rec is not None
    assert rec.remaining_qty == 0
    assert rec.is_fully_closed is True
    assert rec.final_fill_price is not None

    # Audit row settled (no longer a frozen EXECUTED ghost)
    audit = signal_audit_ledger.get(sig.signal_id)
    assert audit.status in ("WON", "LOST", "CLOSED")
    assert audit.exit_reason == "RUNNER_TIME_STOP_HIT"
    assert audit.exit_price is not None

    # FSM residual quantity cleared
    updated = signal_fsm.get(sig.signal_id)
    assert updated.fsm_state == "RUNNER_TIME_STOP_HIT"
    assert updated.remaining_qty == 0


@pytest.mark.asyncio
async def test_worker_eod_settle_squares_off_sweep_converted_runner():
    """At the market-close edge the worker runs sweep_expired() (which converts
    runners to RUNNER_TIME_STOP_HIT) and THEN schedules _settle_eod_positions().
    The settle pass must still square off those sweep-converted positions."""
    from app.signals.worker import AutomatedSignalWorker

    sig = make_runner_signal("SIG-RUNNER-EOD-1")
    signal_fsm._signals[sig.signal_id] = sig

    with patch.object(calendar_service, "can_trade_now", return_value=make_perm(False)):
        with patch("app.signals.worker.MarketService"):
            with patch.object(signal_paper_engine, "close_signal_position", new_callable=AsyncMock) as mock_close:
                worker = AutomatedSignalWorker()
                worker._last_market_open = True
                await worker._settle_eod_positions()

    assert mock_close.await_count == 1
    assert mock_close.await_args.kwargs["reason"] == "EOD_SQUAREOFF"
    assert signal_fsm.get(sig.signal_id).fsm_state == "CLOSED"


@pytest.mark.asyncio
async def test_worker_eod_settle_squares_off_time_stopped_active():
    """A CONFIRMED trade the sweep time-stopped must also be settled at EOD."""
    from app.signals.worker import AutomatedSignalWorker

    now_ms = int(time.time() * 1000)
    sig = make_runner_signal("SIG-ACTIVE-EOD-1")
    sig.fsm_state = "CONFIRMED"
    sig.t1_hit = False
    sig.time_stop_at_utc = now_ms - 1_000
    sig.runner_time_stop_at_utc = None
    sig.t1_fill_timestamp = None
    signal_fsm._signals[sig.signal_id] = sig

    with patch.object(calendar_service, "can_trade_now", return_value=make_perm(False)):
        with patch("app.signals.worker.MarketService"):
            with patch.object(signal_paper_engine, "close_signal_position", new_callable=AsyncMock) as mock_close:
                worker = AutomatedSignalWorker()
                worker._last_market_open = True
                await worker._settle_eod_positions()

    assert mock_close.await_count == 1
    assert signal_fsm.get(sig.signal_id).fsm_state == "CLOSED"


@pytest.mark.asyncio
async def test_db_restored_signal_carries_settleable_paper_order():
    """restore_signals_from_db() must synthesize a paper_order for rows with an
    actual fill, otherwise close_signal_position() (and the EOD square-off)
    refuse to settle restored open positions."""
    from app.signals.signals_persistence import restore_signals_from_db

    now_ms = int(time.time() * 1000)
    row = {
        "signal_id": "SIG-RESTORE-PAPER-1",
        "audit_id": "AUD-RESTORE-PAPER-1",
        "underlying": "NIFTY",
        "strategy": "BREAKOUT",
        "direction": "LONG_CALL",
        "timeframe": "5M",
        "option_symbol": OPTION_CONTRACT["broker_symbol"],
        "option_type": "CE",
        "option_strike": 24900,
        "lot_size": 75,
        "lots": 2,
        "quantity": 150,
        "spot_price_at_creation": 24800.0,
        "trigger_price": 24855.0,
        "stop_loss": 24780.0,
        "current_stop_loss": 24780.0,
        "target_1": 24930.0,
        "target_2": 25000.0,
        "risk_reward_t1": 1.5,
        "risk_reward_t2": 3.0,
        "confidence": 85.0,
        "option_contract": OPTION_CONTRACT,
        "paper_order_id": "ORD-DB-777",
        "paper_side": "BUY",
        "actual_fill_price": 120.0,
        "executed_at_utc": now_ms,
        "state_history": [],
        "created_at_utc": now_ms,
        "updated_at_utc": now_ms,
        "status": "EXECUTED",
    }

    class _FakeResult:
        def mappings(self):
            return self

        def all(self):
            return [row]

    class _FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, *args, **kwargs):
            return _FakeResult()

        async def commit(self):
            return None

    with patch("app.signals.signals_persistence.get_async_session_factory", return_value=lambda: _FakeSession()):
        await restore_signals_from_db()

    inst = signal_fsm.get("SIG-RESTORE-PAPER-1")
    assert inst is not None
    assert inst.fsm_state == "CONFIRMED"
    assert inst.paper_order is not None, "restored executed signal must be settleable"
    assert inst.paper_order["symbol"] == OPTION_CONTRACT["broker_symbol"]
    assert inst.paper_order["quantity"] == 150
    assert inst.paper_order["order_id"] == "ORD-DB-777"

