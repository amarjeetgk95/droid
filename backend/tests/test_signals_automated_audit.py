"""
Tests for Automated Signal Pipeline, Paper Execution, and Profit/Loss Audit Ledger
"""
import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from app.main import app
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.outcome_tracker import outcome_tracker
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.paper_engine import signal_paper_engine
from app.services.paper_service import paper_service


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_all():
    paper_service.reset_portfolio()
    signal_fsm._signals.clear()
    signal_audit_ledger._trades.clear()


@pytest.mark.asyncio
async def test_automated_paper_execution_on_signal_confirmation():
    # 1. Create an ARMED signal
    sig = SignalInstance(
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
        option_contract={
            "broker_symbol": "NSE:NIFTY24DEC24850CE",
            "strike": 24850,
            "option_type": "CE",
            "lot_size": 75,
        },
        fsm_state="ARMED",
    )
    signal_fsm.register(sig)
    signal_audit_ledger.record_signal_created(
        signal_id=sig.signal_id,
        underlying=sig.underlying,
        strategy=sig.strategy,
        direction=sig.direction,
        timeframe=sig.timeframe,
        spot_price=float(sig.spot_price),
        trigger=float(sig.trigger),
        stop_loss=float(sig.stop_loss),
        target_1=float(sig.target_1),
        target_2=float(sig.target_2),
        confidence=float(sig.confidence),
        option_contract=sig.option_contract,
        lots=1,
        status="ARMED",
    )

    # 2. Simulate price crossing trigger -> 24860.0
    events = await outcome_tracker.process_price_update_async("NIFTY", Decimal("24860.0"))
    assert len(events) == 1
    assert events[0]["event"] == "CONFIRMED"

    # Verify FSM state transitioned to CONFIRMED
    updated_sig = signal_fsm.get(sig.signal_id)
    assert updated_sig.fsm_state == "CONFIRMED"
    assert updated_sig.paper_order is not None
    assert updated_sig.paper_order["status"] == "FILLED"

    # Verify audit ledger recorded paper execution
    audit_rec = signal_audit_ledger.get(sig.signal_id)
    assert audit_rec is not None
    assert audit_rec.status == "EXECUTED"
    assert audit_rec.paper_order_id is not None
    assert audit_rec.actual_fill_price is not None
    assert audit_rec.quantity == 75


@pytest.mark.asyncio
async def test_automated_square_off_target_hit_with_actual_pnl():
    # 1. Setup an active executed signal
    sig = SignalInstance(
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
        option_contract={
            "broker_symbol": "NSE:NIFTY24DEC24850CE",
            "strike": 24850,
            "option_type": "CE",
            "lot_size": 75,
        },
        fsm_state="ARMED",
    )
    signal_fsm.register(sig)
    signal_audit_ledger.record_signal_created(
        signal_id=sig.signal_id,
        underlying=sig.underlying,
        strategy=sig.strategy,
        direction=sig.direction,
        timeframe=sig.timeframe,
        spot_price=float(sig.spot_price),
        trigger=float(sig.trigger),
        stop_loss=float(sig.stop_loss),
        target_1=float(sig.target_1),
        target_2=float(sig.target_2),
        confidence=float(sig.confidence),
        option_contract=sig.option_contract,
        lots=1,
        status="ARMED",
    )

    # 2. Trigger and execute
    await outcome_tracker.process_price_update_async("NIFTY", Decimal("24855.0"))

    # 3. Simulate price rising to Target 1 -> 24935.0
    exit_events = await outcome_tracker.process_price_update_async("NIFTY", Decimal("24935.0"))
    assert len(exit_events) == 1
    assert exit_events[0]["event"] == "TARGET_1_HIT"

    # Verify FSM transition
    updated_sig = signal_fsm.get(sig.signal_id)
    assert updated_sig.fsm_state == "TARGET_1_HIT"
    assert updated_sig.outcome_status == "WIN_T1"

    # Verify audit ledger recorded profit and loss
    audit_rec = signal_audit_ledger.get(sig.signal_id)
    assert audit_rec.status == "WON"
    assert audit_rec.is_winner is True
    assert audit_rec.actual_pnl_inr > 0
    assert audit_rec.actual_pnl_points > 0
    assert audit_rec.exit_price == 24935.0
    assert audit_rec.holding_time_str is not None


@pytest.mark.asyncio
async def test_automated_square_off_stop_loss_hit_with_loss_pnl():
    # 1. Setup an active executed signal
    sig = SignalInstance(
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
        option_contract={
            "broker_symbol": "NSE:NIFTY24DEC24850CE",
            "strike": 24850,
            "option_type": "CE",
            "lot_size": 75,
        },
        fsm_state="ARMED",
    )
    signal_fsm.register(sig)
    signal_audit_ledger.record_signal_created(
        signal_id=sig.signal_id,
        underlying=sig.underlying,
        strategy=sig.strategy,
        direction=sig.direction,
        timeframe=sig.timeframe,
        spot_price=float(sig.spot_price),
        trigger=float(sig.trigger),
        stop_loss=float(sig.stop_loss),
        target_1=float(sig.target_1),
        target_2=float(sig.target_2),
        confidence=float(sig.confidence),
        option_contract=sig.option_contract,
        lots=1,
        status="ARMED",
    )

    # 2. Trigger and execute
    await outcome_tracker.process_price_update_async("NIFTY", Decimal("24855.0"))

    # 3. Simulate price falling to Stop Loss -> 24775.0
    exit_events = await outcome_tracker.process_price_update_async("NIFTY", Decimal("24775.0"))
    assert len(exit_events) == 1
    assert exit_events[0]["event"] == "STOP_LOSS_HIT"

    # Verify FSM transition
    updated_sig = signal_fsm.get(sig.signal_id)
    assert updated_sig.fsm_state == "STOP_LOSS_HIT"
    assert updated_sig.outcome_status == "LOSS_SL"

    # Verify audit ledger recorded loss
    audit_rec = signal_audit_ledger.get(sig.signal_id)
    assert audit_rec.status == "LOST"
    assert audit_rec.is_winner is False
    assert audit_rec.actual_pnl_inr < 0
    assert audit_rec.actual_pnl_points < 0
    assert audit_rec.exit_price == 24775.0


def test_signals_audit_api_endpoints(client):
    # 1. Generate signal with paper execution
    res = client.post("/api/v1/signals/generate", json={
        "instrument_id": "NIFTY",
        "candle_timeframe": "5M",
        "direction": "BULLISH",
        "status": "CONFIRMED",
        "trigger_level": 24900.0,
        "current_price": 24900.0,
        "execute_paper": True,
        "notify_telegram": False,
    })
    assert res.status_code == 200
    sig_id = res.json()["signal"]["signal_id"]

    # 2. Query /api/v1/signals/audit
    audit_res = client.get("/api/v1/signals/audit")
    assert audit_res.status_code == 200
    data = audit_res.json()
    assert "trades" in data
    assert "summary" in data
    assert len(data["trades"]) >= 1
    assert data["trades"][0]["signal_id"] == sig_id
    assert data["summary"]["total_signals_audited"] >= 1

    # 3. Query /api/v1/signals/{signal_id}/audit
    single_res = client.get(f"/api/v1/signals/{sig_id}/audit")
    assert single_res.status_code == 200
    single_data = single_res.json()
    assert single_data["signal_id"] == sig_id
    assert single_data["status"] == "EXECUTED"
    assert single_data["actual_fill_price"] is not None
    # Live MTM should be computed
    assert single_data["current_price"] is not None
    assert single_data["unrealized_pnl_inr"] is not None


@pytest.mark.asyncio
async def test_live_mark_to_market_pnl_updates_on_open_trade():
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800.0"),
        entry_min=Decimal("24850.0"),
        entry_max=Decimal("24860.0"),
        trigger=Decimal("24850.0"),
        stop_loss=Decimal("24780.0"),
        target_1=Decimal("24950.0"),
        target_2=Decimal("25050.0"),
        risk_points=Decimal("70.0"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        option_contract={"broker_symbol": "NSE:NIFTY24DEC24850CE", "strike": 24850, "option_type": "CE", "lot_size": 75},
        fsm_state="ARMED",
    )
    signal_fsm.register(sig)
    signal_audit_ledger.record_signal_created(
        signal_id=sig.signal_id,
        underlying=sig.underlying,
        strategy=sig.strategy,
        direction=sig.direction,
        timeframe=sig.timeframe,
        spot_price=float(sig.spot_price),
        trigger=float(sig.trigger),
        stop_loss=float(sig.stop_loss),
        target_1=float(sig.target_1),
        target_2=float(sig.target_2),
        confidence=float(sig.confidence),
        option_contract=sig.option_contract,
        lots=1,
        status="CONFIRMED",
    )
    signal_audit_ledger.record_paper_executed(
        signal_id=sig.signal_id,
        paper_order_id="ORD-TEST-001",
        fill_price=24850.0,
        quantity=75,
        lots=1,
        side="BUY",
        margin_used=24850.0 * 75 * 0.15,
    )

    # 1. Simulate price rising by +30 points to 24880.0
    updated = signal_audit_ledger.update_live_quote("NIFTY", 24880.0)
    assert len(updated) == 1
    rec = updated[0]
    assert rec.current_price == 24880.0
    assert rec.unrealized_pnl_points == 30.0
    assert rec.unrealized_pnl_inr == 30.0 * 75  # 2250.0
    assert rec.is_winner is True
    assert rec.total_pnl_inr == 2250.0
    assert rec.live_duration_str is not None

    # 2. Simulate price falling by -20 points to 24830.0
    signal_audit_ledger.update_live_quote("NIFTY", 24830.0)
    rec2 = signal_audit_ledger.get(sig.signal_id)
    assert rec2.current_price == 24830.0
    assert rec2.unrealized_pnl_points == -20.0
    assert rec2.unrealized_pnl_inr == -20.0 * 75  # -1500.0
    assert rec2.is_winner is False

    # 3. Test summary metrics aggregation
    summary = signal_audit_ledger.get_summary_metrics()
    assert summary["open_trades"] == 1
    assert summary["net_unrealized_pnl_inr"] == -1500.0
    assert summary["total_pnl_inr"] == -1500.0
    assert summary["live_losing_trades"] == 1
    assert summary["live_winning_trades"] == 0

