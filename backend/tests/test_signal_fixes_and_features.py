import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from app.main import app
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.outcome_tracker import outcome_tracker
from app.signals.signals_persistence import ensure_signals_tables, persist_executed_signal, restore_signals_from_db, delete_persisted_signal

@pytest.fixture(autouse=True)
def _open_market(mock_market_open):
    """Ensure market is considered open for signal fixes and features tests."""
    pass


def test_routes_not_shadowed(client: TestClient):
    """Verify /engines and /stream are not shadowed by /{signal_id}."""
    res_engines = client.get("/api/v1/signals/engines")
    assert res_engines.status_code == 200
    assert "approved_universe" in res_engines.json()

    res_history = client.get("/api/v1/signals/history")
    assert res_history.status_code == 200
    assert "data" in res_history.json()

    res_preview = client.post("/api/v1/signals/preview", json={
        "underlying": "NIFTY",
        "direction": "LONG_CALL",
        "status": "CONFIRMED",
        "trigger_level": 24850.0,
        "stop_loss": 24800.0,
    })
    assert res_preview.status_code == 200
    assert "preview" in res_preview.json()


def test_cross_underlying_quote_isolation():
    """Verify updating NIFTY quote does not corrupt BANKNIFTY trades."""
    # Ensure banknifty trade in ledger
    trades = signal_audit_ledger.list_trades()
    bnf_trade = next((t for t in trades if "BANK" in t.underlying), None)
    if bnf_trade is None:
        bnf_trade = signal_audit_ledger.record_signal_created(
            signal_id="sig-bnf-test-isolation",
            underlying="BANKNIFTY",
            strategy="MOMENTUM",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=51000.0,
            trigger=51100.0,
            stop_loss=50900.0,
            target_1=51300.0,
            target_2=51500.0,
        )
    assert bnf_trade is not None
    orig_pnl = bnf_trade.actual_pnl_inr
    orig_price = bnf_trade.current_price

    # Update NIFTY price
    signal_audit_ledger.update_live_quote("NIFTY", 24800.0)
    refreshed_bnf = signal_audit_ledger.get(bnf_trade.signal_id)

    assert refreshed_bnf.current_price == orig_price
    assert refreshed_bnf.actual_pnl_inr == orig_pnl


def test_fsm_transitions():
    """Verify ARMED -> CONFIRMED and VALIDATED -> TRIGGERED are allowed."""
    sig1 = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24805"),
        stop_loss=Decimal("24750"),
        target_1=Decimal("24900"),
        target_2=Decimal("24950"),
        risk_points=Decimal("50"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=80,
        fsm_state="ARMED",
    )
    signal_fsm.register(sig1)
    ok, err = signal_fsm.transition(sig1.signal_id, "CONFIRMED")
    assert ok is True
    assert signal_fsm.get(sig1.signal_id).fsm_state == "CONFIRMED"

    sig2 = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24805"),
        stop_loss=Decimal("24750"),
        target_1=Decimal("24900"),
        target_2=Decimal("24950"),
        risk_points=Decimal("50"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=65,
        fsm_state="VALIDATED",
    )
    signal_fsm.register(sig2)
    ok2, err2 = signal_fsm.transition(sig2.signal_id, "TRIGGERED")
    assert ok2 is True
    assert signal_fsm.get(sig2.signal_id).fsm_state == "TRIGGERED"


def test_target_1_win_not_overwritten_by_stop_loss():
    """Verify a trade won at Target 1 cannot be overwritten as LOST if price later drops."""
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800"),
        entry_min=Decimal("24800"),
        entry_max=Decimal("24810"),
        trigger=Decimal("24805"),
        stop_loss=Decimal("24750"),
        target_1=Decimal("24900"),
        target_2=Decimal("24950"),
        risk_points=Decimal("50"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=80,
        fsm_state="CONFIRMED",
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
        status="CONFIRMED",
    )
    signal_audit_ledger.record_paper_executed(
        signal_id=sig.signal_id,
        paper_order_id="ORD-TEST-1",
        fill_price=24805.0,
        quantity=75,
        lots=1,
    )

    # Price rises to Target 1
    events = outcome_tracker.update_with_price("NIFTY", Decimal("24905.0"), allow_closed_market=True)
    assert any(e["event"] == "TARGET_1_HIT" for e in events)

    updated_sig = signal_fsm.get(sig.signal_id)
    assert updated_sig.fsm_state == "TARGET_1_HIT"
    assert updated_sig.outcome_status == "WIN_T1"

    # Price later plummets to Stop Loss
    events2 = outcome_tracker.update_with_price("NIFTY", Decimal("24740.0"), allow_closed_market=True)
    # Should NOT trigger stop loss hit for this won signal
    assert not any(e.get("signal_id") == sig.signal_id and e.get("event") == "STOP_LOSS_HIT" for e in events2)
    assert signal_fsm.get(sig.signal_id).fsm_state == "TARGET_1_HIT"


def test_put_signal_math(client: TestClient):
    """Verify BEARISH / LONG_PUT signals calculate SL above entry and targets below entry with positive R:R."""
    res = client.post("/api/v1/signals/generate", json={
        "underlying": "NIFTY",
        "direction": "LONG_PUT",
        "strategy": "BREAKOUT",
        "current_price": 24800.0,
        "timeframe": "5M",
    })
    assert res.status_code == 200
    data = res.json()["signal"]
    assert data["direction"] == "BEARISH"
    assert float(data["stop_loss"]) > float(data["entry_min"])
    assert float(data["target_1"]) < float(data["entry_min"])
    assert float(data["target_2"]) < float(data["target_1"])
    assert float(data["risk_reward_t1"]) > 0
    assert float(data["risk_reward_t2"]) > 0


def test_paper_wallet_capital(client: TestClient):
    """Verify custom paper trading wallet capital endpoint."""
    res = client.post("/api/v1/signals/paper-wallet", json={"capital": 500000.0})
    assert res.status_code == 200
    assert res.json()["capital"] == 500000.0


def test_signal_delete(client: TestClient):
    """Verify signal deletion authority removes signal from FSM and ledger."""
    # Create signal
    gen = client.post("/api/v1/signals/generate", json={
        "underlying": "NIFTY",
        "direction": "LONG_CALL",
        "strategy": "ORB",
        "current_price": 24800.0,
    }).json()
    sid = gen["signal"]["signal_id"]

    # Verify exists
    assert signal_fsm.get(sid) is not None
    assert signal_audit_ledger.get(sid) is not None

    # Delete
    del_res = client.delete(f"/api/v1/signals/{sid}")
    assert del_res.status_code == 200
    assert del_res.json()["status"] == "success"

    # Verify removed
    assert signal_fsm.get(sid) is None
    assert signal_audit_ledger.get(sid) is None
