"""Regression tests for 11 reported signal-module defects (domain mixing, lifecycle, gates).

Covers: PUT PnL direction, MTM domain, slippage domain, no-fill square-off domain,
T1 partial close, delete-without-exit-price, FSM degraded guard, scalp trigger
floors, BANKNIFTY plausibility, runner in summary, worker task retention.
"""
import asyncio
from decimal import Decimal

import pytest

import pytest

from app.signals.audit_ledger import SignalAuditLedger
from app.signals.fsm import SignalFSMManager, SignalInstance, signal_fsm
from app.signals.trigger_gate import check_trigger_integrity


@pytest.fixture(autouse=True)
def _isolate_global_paper_state():
    from app.services.paper_service import paper_service
    paper_service.reset_portfolio()
    yield
    paper_service.reset_portfolio()


OPT_CE = {"broker_symbol": "NSE:NIFTY26SEP25100CE", "option_type": "CE",
          "strike": 25100.0, "lot_size": 75}
OPT_PE = {"broker_symbol": "NSE:NIFTY26SEP25000PE", "option_type": "PE",
          "strike": 25000.0, "lot_size": 75}


def _make_ledger() -> SignalAuditLedger:
    return SignalAuditLedger()


def test_put_buy_win_recorded_as_win():
    """Issue 1: long PUT 100 -> 150 must be +Rs 3,750 WON, not a loss."""
    ledger = _make_ledger()
    ledger.record_signal_created(
        signal_id="T-PUT-1", underlying="NIFTY", strategy="MEAN_REVERSION",
        direction="LONG_PUT", timeframe="5M", spot_price=25100.0, trigger=25090.0,
        stop_loss=25120.0, target_1=25040.0, target_2=25000.0,
        option_contract=dict(OPT_PE), lots=1, status="ARMED")
    ledger.record_paper_executed(signal_id="T-PUT-1", paper_order_id="ORD-1",
                                 fill_price=100.0, quantity=75, lots=1, side="BUY")
    sq = ledger.record_square_off(signal_id="T-PUT-1", exit_price=150.0,
                                  exit_reason="TARGET_1_HIT")
    assert sq is not None
    assert sq.actual_pnl_inr == pytest.approx(3750.0)
    assert sq.status == "WON"
    assert sq.is_winner is True


def test_mtm_stays_in_option_domain():
    """Issue 2: spot 25,050 vs 150 fill must not print ~Rs 18.6L phantom MTM."""
    ledger = _make_ledger()
    ledger.record_signal_created(
        signal_id="T-MTM-1", underlying="NIFTY", strategy="BREAKOUT",
        direction="LONG_CALL", timeframe="5M", spot_price=25100.0, trigger=25110.0,
        stop_loss=25090.0, target_1=25140.0, target_2=25170.0,
        option_contract=dict(OPT_CE), lots=1, status="ARMED")
    ledger.record_paper_executed(signal_id="T-MTM-1", paper_order_id="ORD-2",
                                 fill_price=150.0, quantity=75, lots=1, side="BUY")
    updated = ledger.update_live_quote("NIFTY", 25050.0)
    rec = next(r for r in updated if r.signal_id == "T-MTM-1")
    assert abs(rec.unrealized_pnl_inr or 0.0) < 100000.0


def test_slippage_measured_in_premium_domain():
    """Issue 4: slippage must compare premium vs premium, not premium vs spot."""
    ledger = _make_ledger()
    ledger.record_signal_created(
        signal_id="T-SLIP-1", underlying="NIFTY", strategy="BREAKOUT",
        direction="LONG_CALL", timeframe="5M", spot_price=25100.0, trigger=25000.0,
        stop_loss=25090.0, target_1=25140.0, target_2=25170.0,
        option_contract=dict(OPT_CE), lots=1, status="ARMED")
    ledger.record_paper_executed(signal_id="T-SLIP-1", paper_order_id="ORD-3",
                                 fill_price=150.0, quantity=75, lots=1, side="BUY")
    rec = ledger.get("T-SLIP-1")
    assert rec is not None and rec.slippage_points is not None
    assert abs(rec.slippage_points) < 100.0


def test_square_off_without_fill_stays_in_domain():
    """Residual: option exit with no fill must use estimated premium entry, not spot."""
    ledger = _make_ledger()
    ledger.record_signal_created(
        signal_id="T-NOFILL-1", underlying="NIFTY", strategy="BREAKOUT",
        direction="LONG_CALL", timeframe="5M", spot_price=25100.0, trigger=25110.0,
        stop_loss=25090.0, target_1=25140.0, target_2=25170.0,
        option_contract=dict(OPT_CE), lots=1, status="CONFIRMED")
    sq = ledger.record_square_off(signal_id="T-NOFILL-1", exit_price=136.09,
                                  exit_reason="DELETED_BY_USER")
    assert sq is not None
    assert abs(sq.actual_pnl_inr or 0.0) < 100000.0


def _register_global_frozen_signal(signal_id: str):
    sig = SignalInstance(
        underlying="NIFTY", strategy="BREAKOUT", direction="LONG_CALL",
        timeframe="5M", spot_price=Decimal("25100"),
        entry_min=Decimal("25100"), entry_max=Decimal("25105"),
        trigger=Decimal("25110"), stop_loss=Decimal("25090"),
        target_1=Decimal("25140"), target_2=Decimal("25170"),
        risk_points=Decimal("20"), risk_reward_t1=1.5, risk_reward_t2=3.0,
        confidence=75.0, fsm_state="CONFIRMED",
        option_contract={"broker_symbol": "NSE:NIFTY26SEP25100CE",
                         "option_type": "CE", "strike": 25100.0,
                         "lot_size": 75, "lots": 1},
        paper_order={"symbol": "NSE:NIFTY26SEP25100CE", "quantity": 75})
    sig.signal_id = signal_id
    signal_fsm.register(sig)
    from app.signals.audit_ledger import signal_audit_ledger
    signal_audit_ledger.record_signal_created(
        signal_id=signal_id, underlying="NIFTY", strategy="BREAKOUT",
        direction="LONG_CALL", timeframe="5M", spot_price=25100.0,
        trigger=25110.0, stop_loss=25090.0, target_1=25140.0,
        target_2=25170.0, confidence=75.0,
        option_contract={"broker_symbol": "NSE:NIFTY26SEP25100CE",
                         "option_type": "CE", "strike": 25100.0,
                         "lot_size": 75}, lots=1, status="CONFIRMED")
    return signal_id


def test_t1_partial_does_not_full_close():
    """Issue 5: TARGET_1_HIT partial must leave audit record open for the runner."""
    from app.signals.paper_engine import signal_paper_engine
    from app.signals.audit_ledger import signal_audit_ledger
    from app.services.paper_service import paper_service
    from app.models.paper import OrderPayload
    sid = _register_global_frozen_signal("T-PARTIAL-1")
    symbol = "NSE:NIFTY26SEP25100CE"
    try:
        asyncio.run(paper_service.place_order(OrderPayload(
            symbol=symbol, underlying="NIFTY", side="BUY",
            order_type="MARKET", product="INTRADAY", quantity=150,
            price=150.0), allow_closed_market=True))
        rec = asyncio.run(signal_paper_engine.close_signal_position(
            sid, exit_price=160.0, reason="TARGET_1_HIT", quantity_to_close=75,
            allow_closed_market=True))
        assert rec is not None
        assert signal_audit_ledger.get(sid).status == "TARGET_1_HIT"
        # Runner exit must still settle afterwards (guard previously swallowed it).
        rec2 = signal_audit_ledger.record_square_off(
            signal_id=sid, exit_price=170.0, exit_reason="TARGET_2_HIT")
        assert rec2 is not None and rec2.status == "WON"
    finally:
        try:
            asyncio.run(signal_paper_engine.close_signal_position(
                sid, exit_price=170.0, reason="TEST_CLEANUP",
                allow_closed_market=True))
        except Exception:
            pass
        signal_fsm.delete(sid)
        signal_audit_ledger.delete_trade(sid)


def test_delete_path_without_exit_price():
    """Issue 6: close_signal_position must resolve exit itself, never TypeError."""
    from app.signals.paper_engine import signal_paper_engine
    from app.signals.audit_ledger import signal_audit_ledger
    sid = _register_global_frozen_signal("T-DELETE-1")
    try:
        rec = asyncio.run(signal_paper_engine.close_signal_position(
            sid, reason="DELETED_BY_USER"))
        assert rec is not None
    finally:
        signal_fsm.delete(sid)
        signal_audit_ledger.delete_trade(sid)


def test_fsm_blocks_degraded_trigger():
    """Issue 7: degraded-F&O signals cannot TRIGGER/CONFIRM."""
    fsm = SignalFSMManager()
    sig = SignalInstance(
        underlying="NIFTY", strategy="BREAKOUT", direction="LONG_CALL",
        timeframe="5M", spot_price=Decimal("25100"),
        entry_min=Decimal("25100"), entry_max=Decimal("25105"),
        trigger=Decimal("25110"), stop_loss=Decimal("25090"),
        target_1=Decimal("25140"), target_2=Decimal("25170"),
        risk_points=Decimal("20"), risk_reward_t1=1.5, risk_reward_t2=3.0,
        confidence=75.0, fsm_state="VALIDATED",
        confluence_breakdown={"fno_degraded": True})
    fsm.register(sig)
    ok, err = fsm.transition(sig.signal_id, "TRIGGERED",
                             market_price=Decimal("25110"),
                             reason="TRIGGER_LEVEL_HIT")
    assert ok is False
    assert err == "FNO_DATA_DEGRADED_CANNOT_ARM"


def test_outcome_tracker_honors_fsm_rejection():
    """Issue 7 (tracker half): transition failure must skip paper execution."""
    import inspect
    from app.signals.outcome_tracker import SignalOutcomeTracker
    src = inspect.getsource(SignalOutcomeTracker.process_price_update_async)
    assert "if not ok" in src


def test_scalp_trigger_floors_desk_differentiated():
    """Issue 8: tight 1M offsets pass as scalp, fail as intraday."""
    kw = dict(direction="LONG_CALL", spot_price=Decimal("25100"),
              entry_min=Decimal("25100"), entry_max=Decimal("25103"),
              trigger=Decimal("25103.0"), stop_loss=Decimal("25093"),
              target_1=Decimal("25113.5"), target_2=Decimal("25124"),
              risk_points=Decimal("10.0"))
    intraday = check_trigger_integrity(**kw)
    scalp = check_trigger_integrity(**kw, is_scalp=True, timeframe="1M")
    assert intraday.passed is False
    assert intraday.reason_code == "TRIGGER_TOO_CLOSE"
    assert scalp.passed is True


def test_banknifty_52k_survives_sanitize():
    """Issue 9: legitimate 52k BANKNIFTY records must not be purged; ghosts must."""
    from app.signals.audit_ledger import signal_audit_ledger
    from app.signals.signals_persistence import sanitize_persisted_signals
    for sid, spot in (("T-BNF-52K", 52000.0), ("T-BNF-GHOST", 39000.0)):
        signal_audit_ledger.record_signal_created(
            signal_id=sid, underlying="BANKNIFTY", strategy="BREAKOUT",
            direction="LONG_CALL", timeframe="5M", spot_price=spot,
            trigger=spot + 10.0, stop_loss=spot - 60.0,
            target_1=spot + 100.0, target_2=spot + 180.0, lots=1,
            status="ARMED")
    try:
        sanitize_persisted_signals()
        assert signal_audit_ledger.get("T-BNF-52K") is not None
        assert signal_audit_ledger.get("T-BNF-GHOST") is None
    finally:
        signal_audit_ledger.delete_trade("T-BNF-52K")
        signal_audit_ledger.delete_trade("T-BNF-GHOST")


def test_runner_in_summary_metrics():
    """Issue 10: TARGET_1_HIT runners count as open exposure."""
    ledger = _make_ledger()
    ledger.record_signal_created(
        signal_id="T-RUN-1", underlying="NIFTY", strategy="BREAKOUT",
        direction="LONG_CALL", timeframe="5M", spot_price=25100.0,
        trigger=25110.0, stop_loss=25090.0, target_1=25140.0,
        target_2=25170.0, option_contract=dict(OPT_CE), lots=1,
        status="ARMED")
    ledger.record_state_transition(signal_id="T-RUN-1", to_state="TARGET_1_HIT",
                                   market_price=25140.0, reason="TEST")
    assert ledger.get_summary_metrics()["open_trades"] >= 1


def test_worker_retains_bg_tasks():
    """Issue 11: fire-and-forget telemetry tasks must be strongly referenced."""
    from app.signals.worker import AutomatedSignalWorker
    worker = AutomatedSignalWorker()
    assert isinstance(worker._bg_tasks, set)


NIFTY_PUT_23800 = {"broker_symbol": "NSE:NIFTY26SEP1023800PE", "option_type": "PE",
                   "strike": 23800.0, "lot_size": 75}


def test_friction_uses_exit_premium_not_spot_tick():
    """FSM R must be premium-vs-premium for option signals.

    Regression for the ledger's poisoned performance metrics: feeding a spot
    exit tick (e.g. 23773) against a premium entry (118.75) fabricated ~8R of
    friction and turned every win's realized_rr_net deeply negative.
    """
    from app.signals.fsm import SignalFSMManager, SignalInstance
    fsm = SignalFSMManager()
    sig = SignalInstance(
        underlying="NIFTY", strategy="TREND_PULLBACK", direction="LONG_PUT",
        timeframe="5M", spot_price=Decimal("23807.10"),
        entry_min=Decimal("23807.10"), entry_max=Decimal("23807.10"),
        trigger=Decimal("23807.10"), stop_loss=Decimal("23825.10"),
        target_1=Decimal("23773.50"), target_2=Decimal("23753.34"),
        risk_points=Decimal("18"), risk_reward_t1=1.5, risk_reward_t2=2.5,
        confidence=69.0, fsm_state="CONFIRMED",
        actual_fill_price=Decimal("118.75"), entry_price=Decimal("118.75"),
        lots=1, option_contract=dict(NIFTY_PUT_23800),
    )
    fsm.register(sig)
    fsm.transition(sig.signal_id, "TARGET_1_HIT", market_price=Decimal("23773.50"),
                   reason="TARGET_1_ACHIEVED")
    assert sig.realized_rr_gross == 1.5
    assert sig.realized_rr_net is not None
    assert 0.0 < sig.realized_rr_net < sig.realized_rr_gross


def test_breakeven_ratchet_stays_in_spot_domain():
    """BE ratchet must move the spot stop to the spot entry zone, never to the
    option premium fill (₹118 premium as a ₹23807-scale stop = instant phantom
    STOP_LOSS_HIT on the next tick)."""
    from app.signals.fsm import SignalFSMManager, SignalInstance, evaluate_tick
    fsm = SignalFSMManager()
    sig = SignalInstance(
        underlying="NIFTY", strategy="TREND_PULLBACK", direction="LONG_PUT",
        timeframe="5M", spot_price=Decimal("23807.10"),
        entry_min=Decimal("23807.10"), entry_max=Decimal("23807.10"),
        trigger=Decimal("23807.10"), stop_loss=Decimal("23825.10"),
        target_1=Decimal("23773.50"), target_2=Decimal("23753.34"),
        risk_points=Decimal("18"), risk_reward_t1=1.5, risk_reward_t2=2.5,
        confidence=69.0, fsm_state="CONFIRMED",
        actual_fill_price=Decimal("118.75"), entry_price=Decimal("118.75"),
        option_contract=dict(NIFTY_PUT_23800),
    )
    fsm.register(sig)
    assert fsm.ratchet_breakeven(sig.signal_id, Decimal("23790")) is True
    assert float(sig.current_stop_loss) > 5000.0
    action, _ = evaluate_tick(sig, Decimal("23800"), None)
    assert action != "STOP_LOSS_HIT"
