"""Phase 2b-1: unified paper-trade PnL and terminal-state ordering.

Pins the post-consolidation contracts:

1. ONE realized-PnL source: ``record_square_off`` books the fill reconciler's
   net figure (T1 leg + runner leg exactly once, statutory costs included)
   whenever a non-synthetic reconciliation record exists; the previous gross
   computation remains only as the audit-only / NO_MARK fallback.
2. T1 partial accounting is independent of ``sync_with_paper_service``: a sync
   between T1 and the runner exit can no longer shrink the trade quantity and
   under-count (or shift) the final booked PnL.
3. Terminal-state ordering: the outcome tracker settles the paper position
   BEFORE writing the terminal FSM state; a rejected exit leaves the signal in
   its pre-close state and the next tick retries. The worker EOD pass never
   forces CLOSED on a failed close.
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.paper import OrderPayload
from app.quant.costs import calculate_option_costs
from app.services.calendar_service import MarketSessionPermission, calendar_service
from app.services.paper_service import paper_service
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.fill_reconciler import option_fill_reconciler
from app.signals.fsm import SignalInstance, signal_fsm
from app.signals.outcome_tracker import outcome_tracker
from app.signals.paper_engine import SignalPaperExecutionResult, signal_paper_engine
from tests.conftest import seed_chain_mark

SYMBOL = "NSE:NIFTY26SEP24800CE"
CONTRACT = {
    "broker_symbol": SYMBOL,
    "strike": 24800.0,
    "option_type": "CE",
    "lot_size": 75,
}


@pytest.fixture(autouse=True)
def _isolate_pnl_state(tmp_path, monkeypatch):
    # Keep the intent ledger's on-disk persistence out of the repo root.
    import importlib

    _intent_mod = importlib.import_module("app.signals.execution_intent")
    monkeypatch.setattr(_intent_mod, "_INTENT_LEDGER_FILE", tmp_path / "intent_ledger.json")

    paper_service.reset_portfolio()
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()
    option_fill_reconciler._records.clear()
    yield
    paper_service.reset_portfolio()
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()
    option_fill_reconciler._records.clear()


def _leg_net(entry: float, exit_price: float, qty: int) -> float:
    """Independently reproduce one reconciler stage: gross move - statutory costs."""
    buy_turnover = round(entry * qty, 2)
    sell_turnover = round(exit_price * qty, 2)
    costs = calculate_option_costs(buy_turnover=buy_turnover, sell_turnover=sell_turnover, num_orders=2)
    gross = round(sell_turnover - buy_turnover, 2)
    return round(gross - costs.total_cost, 2)


def _register_signal(
    signal_id: str,
    *,
    entry: float = 100.0,
    quantity: int = 150,
    fsm_state: str = "TARGET_1_HIT",
    t1_done: bool = True,
) -> SignalInstance:
    sig = SignalInstance(
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24795"),
        entry_max=Decimal("24805"),
        trigger=Decimal("24800"),
        stop_loss=Decimal("24720"),
        target_1=Decimal("24920"),
        target_2=Decimal("25000"),
        risk_points=Decimal("80"),
        risk_reward_t1=1.5,
        risk_reward_t2=2.5,
        confidence=85.0,
        lots=max(1, quantity // 75),
        option_contract=dict(CONTRACT),
        fsm_state=fsm_state,
        t1_hit=t1_done,
        actual_fill_price=Decimal(str(entry)),
        entry_price=Decimal(str(entry)),
        intended_qty=Decimal(str(quantity)),
        remaining_qty=Decimal(str(75 if t1_done else quantity)),
        paper_order={
            "symbol": SYMBOL,
            "quantity": quantity,
            "lots": max(1, quantity // 75),
            "order_id": f"ORD-{signal_id}",
            "status": "FILLED",
            "side": "BUY",
            "fill_price": entry,
        },
    )
    signal_fsm.register(sig)
    return sig


def _seed_audit(signal_id: str, entry: float, quantity: int) -> None:
    signal_audit_ledger.record_signal_created(
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=24800.0,
        trigger=24800.0,
        stop_loss=24720.0,
        target_1=24920.0,
        target_2=25000.0,
        confidence=85.0,
        option_contract=dict(CONTRACT),
        lots=max(1, quantity // 75),
        status="ARMED",
    )
    signal_audit_ledger.record_paper_executed(
        signal_id=signal_id,
        paper_order_id=f"ORD-{signal_id}",
        fill_price=entry,
        quantity=quantity,
        lots=max(1, quantity // 75),
        side="BUY",
        margin_used=entry * quantity,
    )


def _seed_two_leg_reconciliation(sig: SignalInstance, entry: float, t1_exit: float) -> None:
    option_fill_reconciler.reconcile_entry(sig, entry, int(sig.intended_qty), 75)
    option_fill_reconciler.reconcile_t1_exit(sig, t1_exit, int(time.time() * 1000))


def _close_failure_result(signal_id: str, quantity: int = 75) -> SignalPaperExecutionResult:
    return SignalPaperExecutionResult(
        success=False,
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        side="SELL",
        quantity=quantity,
        lots=1,
        fill_price=0.0,
        stop_loss=24720.0,
        target_1=24920.0,
        target_2=25000.0,
        order_id=f"EXIT-REJ-{signal_id}",
        status="REJECTED",
        message="MARKET_QUOTE_UNAVAILABLE: no broker quote to fill market order",
        fill_source="NONE",
        chain_mark_at_fill=None,
    )


def _close_success_result(signal_id: str, quantity: int = 75) -> SignalPaperExecutionResult:
    return SignalPaperExecutionResult(
        success=True,
        signal_id=signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        side="SELL",
        quantity=quantity,
        lots=1,
        fill_price=100.0,
        stop_loss=24720.0,
        target_1=24920.0,
        target_2=25000.0,
        order_id=f"EXIT-OK-{signal_id}",
        status="FILLED",
        message="FILLED",
        fill_source="CHAIN",
        chain_mark_at_fill=100.0,
    )


def _market_perm(allowed: bool) -> MarketSessionPermission:
    now_ist = datetime.now(timezone(timedelta(hours=5, minutes=30)))
    return MarketSessionPermission(
        allowed=allowed,
        reason="MARKET_OPEN" if allowed else "MARKET_CLOSED",
        exchange="NSE",
        session="REGULAR" if allowed else "CLOSED",
        timestamp_ist=now_ist,
        market_open=now_ist.replace(hour=9, minute=15),
        market_close=now_ist.replace(hour=15, minute=30),
    )


# ── 1. ONE PnL SOURCE: reconciler net for final settlement ──────────────


def test_t1_partial_plus_runner_equals_reconciler_net_exactly_once():
    """T1 75 @150 + runner 75 @200 == net(T1 leg) + net(runner leg), once."""
    sid = "SIG-PNL-T1-NOSYNC"
    entry, t1_exit, final_exit = 100.0, 150.0, 200.0
    sig = _register_signal(sid, entry=entry, quantity=150)
    _seed_audit(sid, entry, 150)
    _seed_two_leg_reconciliation(sig, entry, t1_exit)

    closed = signal_audit_ledger.record_square_off(sid, exit_price=final_exit, exit_reason="TARGET_2_HIT")

    recon = option_fill_reconciler.get_reconciliation(sid)
    expected = round(_leg_net(entry, t1_exit, 75) + _leg_net(entry, final_exit, 75), 2)
    assert recon is not None and recon.is_fully_closed is True
    assert recon.net_realized_pnl_inr == pytest.approx(expected)
    assert closed.actual_pnl_inr == pytest.approx(expected)
    assert closed.actual_pnl_inr == pytest.approx(recon.net_realized_pnl_inr)
    assert closed.total_pnl_inr == pytest.approx(expected)
    # Blended gross points across BOTH legs on the intended quantity (11250/150).
    assert closed.actual_pnl_points == pytest.approx(75.0)
    assert closed.status == "WON"
    assert closed.exit_price == pytest.approx(final_exit)
    # Neither the old full-quantity gross nor the residual-only gross.
    assert closed.actual_pnl_inr != pytest.approx((final_exit - entry) * 150)
    assert closed.actual_pnl_inr != pytest.approx((final_exit - entry) * 75)


def test_t1_partial_plus_runner_unchanged_when_sync_runs_between():
    """A sync between T1 and the runner exit must not shift the booked PnL."""
    sid = "SIG-PNL-T1-SYNC"
    entry, t1_exit, final_exit = 100.0, 150.0, 200.0
    sig = _register_signal(sid, entry=entry, quantity=150)
    _seed_audit(sid, entry, 150)
    _seed_two_leg_reconciliation(sig, entry, t1_exit)

    # The live position only holds the post-T1 residual (75). A sync used to
    # rewrite rec.quantity to this residual, corrupting the gross fallback.
    residual = SimpleNamespace(
        is_open=True,
        signal_id=sid,
        order_id=f"ORD-{sid}",
        broker_order_id=None,
        symbol=SYMBOL,
        average_price=entry,
        quantity=75,
        ltp=t1_exit,
        unrealized_pnl=0.0,
    )
    fake_svc = SimpleNamespace(_positions={f"{SYMBOL}_INTRADAY": residual})
    signal_audit_ledger.sync_with_paper_service(fake_svc)

    # The audit trade quantity is the intended 150, not the residual 75.
    assert signal_audit_ledger.get(sid).quantity == 150

    closed = signal_audit_ledger.record_square_off(sid, exit_price=final_exit, exit_reason="TARGET_2_HIT")

    recon = option_fill_reconciler.get_reconciliation(sid)
    expected = round(_leg_net(entry, t1_exit, 75) + _leg_net(entry, final_exit, 75), 2)
    assert recon.net_realized_pnl_inr == pytest.approx(expected)
    assert closed.actual_pnl_inr == pytest.approx(expected)
    assert closed.actual_pnl_points == pytest.approx(75.0)


def test_sync_between_t1_and_final_keeps_gross_fallback_on_intended_quantity():
    """No reconciler: the gross fallback still prices the whole intended trade."""
    sid = "SIG-PNL-SYNC-GROSS"
    _register_signal(sid, entry=100.0, quantity=150)
    _seed_audit(sid, 100.0, 150)
    assert option_fill_reconciler.get_reconciliation(sid) is None

    residual = SimpleNamespace(
        is_open=True,
        signal_id=sid,
        order_id=f"ORD-{sid}",
        broker_order_id=None,
        symbol=SYMBOL,
        average_price=100.0,
        quantity=75,
        ltp=150.0,
        unrealized_pnl=0.0,
    )
    signal_audit_ledger.sync_with_paper_service(SimpleNamespace(_positions={f"{SYMBOL}_INTRADAY": residual}))
    assert signal_audit_ledger.get(sid).quantity == 150

    closed = signal_audit_ledger.record_square_off(sid, exit_price=200.0, exit_reason="TARGET_2_HIT")
    assert closed.actual_pnl_inr == pytest.approx((200.0 - 100.0) * 150)


def test_direct_close_path_books_reconciler_net_when_reconciliation_exists():
    """Delete/EOD callers of record_square_off get the reconciler net, not gross."""
    sid = "SIG-PNL-DIRECT"
    entry, exit_price = 100.0, 180.0
    sig = _register_signal(sid, entry=entry, quantity=150, fsm_state="CONFIRMED", t1_done=False)
    _seed_audit(sid, entry, 150)
    option_fill_reconciler.reconcile_entry(sig, entry, 150, 75)

    closed = signal_audit_ledger.record_square_off(sid, exit_price=exit_price, exit_reason="DELETED_BY_USER")

    recon = option_fill_reconciler.get_reconciliation(sid)
    expected = _leg_net(entry, exit_price, 150)
    assert recon.is_fully_closed is True
    assert recon.net_realized_pnl_inr == pytest.approx(expected)
    assert closed.actual_pnl_inr == pytest.approx(expected)
    assert closed.actual_pnl_inr < (exit_price - entry) * 150  # costs deducted


def test_audit_only_close_without_reconciliation_keeps_gross_fallback():
    """No reconciliation record (audit-only) → previous gross computation stands."""
    sid = "SIG-PNL-GROSS-ONLY"
    _register_signal(sid, entry=100.0, quantity=75, fsm_state="CONFIRMED", t1_done=False)
    _seed_audit(sid, 100.0, 75)
    assert option_fill_reconciler.get_reconciliation(sid) is None

    closed = signal_audit_ledger.record_square_off(sid, exit_price=150.0, exit_reason="TARGET_1_HIT")

    assert closed.actual_pnl_inr == pytest.approx(3750.0)
    assert closed.actual_pnl_points == pytest.approx(50.0)
    assert closed.total_pnl_inr == pytest.approx(3750.0)
    assert closed.status == "WON"


# ── 2. TERMINAL-STATE ORDERING: outcome tracker ─────────────────────────


@pytest.mark.asyncio
async def test_outcome_tracker_rejected_close_defers_terminal_state_and_retries(
    mock_market_open, paper_fills_from_marks
):
    sid = "SIG-PNL-OT-RETRY"
    entry = 100.0
    seed_chain_mark(SYMBOL, entry, underlying="NIFTY", strike=24800.0, option_type="CE")
    sig = _register_signal(sid, entry=entry, quantity=75, fsm_state="CONFIRMED", t1_done=False)
    _seed_audit(sid, entry, 75)
    option_fill_reconciler.reconcile_entry(sig, entry, 75, 75)

    # Real open virtual position so the retry can actually fill its exit.
    entry_order = await paper_service.place_order(
        OrderPayload(
            symbol=SYMBOL,
            underlying="NIFTY",
            side="BUY",
            order_type="MARKET",
            product="INTRADAY",
            quantity=75,
            price=entry,
        ),
        allow_closed_market=True,
    )
    assert entry_order.status == "FILLED"
    assert paper_service._positions[f"{SYMBOL}_INTRADAY"].is_open is True

    t0 = int(time.time() * 1000)
    failure = _close_failure_result(sid, quantity=75)
    with patch.object(
        signal_paper_engine, "close_signal_position", new=AsyncMock(return_value=failure)
    ) as mock_close:
        events = await outcome_tracker.process_price_update_async(
            "NIFTY", Decimal("24700"), now_ms=t0, allow_closed_market=True
        )

    assert mock_close.await_count == 1
    assert any(e.get("settlement") == "DEFERRED_EXIT_NOT_FILLED" for e in events)

    # Rejected close: FSM non-terminal, position/audit/reconciler untouched.
    assert signal_fsm.get(sid).fsm_state == "CONFIRMED"
    assert paper_service._positions[f"{SYMBOL}_INTRADAY"].is_open is True
    audit_open = signal_audit_ledger.get(sid)
    assert audit_open.status == "EXECUTED"
    assert audit_open.actual_pnl_inr is None
    recon_open = option_fill_reconciler.get_reconciliation(sid)
    assert recon_open.is_fully_closed is False
    assert recon_open.remaining_qty == 75

    # Next tick (fresh timestamp) retries against the real engine and settles.
    seed_chain_mark(SYMBOL, 90.0, underlying="NIFTY", strike=24800.0, option_type="CE")
    retry_events = await outcome_tracker.process_price_update_async(
        "NIFTY", Decimal("24700"), now_ms=t0 + 60_000, allow_closed_market=True
    )
    assert any(e.get("event") == "STOP_LOSS_HIT" for e in retry_events)

    settled = signal_fsm.get(sid)
    assert settled.fsm_state == "STOP_LOSS_HIT"
    assert settled.remaining_qty == Decimal("0")
    assert paper_service._positions[f"{SYMBOL}_INTRADAY"].is_open is False

    final = signal_audit_ledger.get(sid)
    final_recon = option_fill_reconciler.get_reconciliation(sid)
    assert final.status == "LOST"
    assert final_recon.is_fully_closed is True
    assert final.actual_pnl_inr == pytest.approx(final_recon.net_realized_pnl_inr)
    assert final.actual_pnl_inr < 0


# ── 3. TERMINAL-STATE ORDERING: worker EOD settle ───────────────────────


@pytest.mark.asyncio
async def test_worker_eod_rejected_close_retains_signal_and_retries_to_closed_once():
    from app.signals.worker import AutomatedSignalWorker

    sid = "SIG-PNL-EOD-RETRY"
    _register_signal(sid, entry=100.0, quantity=75, fsm_state="CONFIRMED", t1_done=False)
    _seed_audit(sid, 100.0, 75)

    rejected = _close_failure_result(sid, quantity=75)
    with patch.object(calendar_service, "can_trade_now", return_value=_market_perm(False)), \
         patch("app.signals.worker.MarketService"), \
         patch.object(
             signal_paper_engine, "close_signal_position", new=AsyncMock(return_value=rejected)
         ) as mock_close:
        worker = AutomatedSignalWorker()
        worker._last_market_open = True
        await worker._settle_eod_positions()

    # Failed close → no forced CLOSED, nothing claimed/skipped.
    assert mock_close.await_count == 1
    assert signal_fsm.get(sid).fsm_state == "CONFIRMED"
    assert signal_audit_ledger.get(sid).status == "EXECUTED"

    # Next pass succeeds → CLOSED exactly once, never re-settled.
    success = _close_success_result(sid, quantity=75)
    with patch.object(calendar_service, "can_trade_now", return_value=_market_perm(False)), \
         patch("app.signals.worker.MarketService"), \
         patch.object(
             signal_paper_engine, "close_signal_position", new=AsyncMock(return_value=success)
         ) as ok_close:
        await worker._settle_eod_positions()
        assert signal_fsm.get(sid).fsm_state == "CLOSED"
        await worker._settle_eod_positions()

    assert ok_close.await_count == 1
    settled = signal_fsm.get(sid)
    assert settled.fsm_state == "CLOSED"
    closed_events = [h for h in settled.state_history if h.to_state == "CLOSED"]
    assert len(closed_events) == 1
