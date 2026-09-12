"""
Unified Signal & Execution Engine v3.0 Comprehensive Test Suite
Tests:
  - 3-Domain Decoupled FSMs (Signal, Execution Intent, Position)
  - Deterministic SHA-256 Idempotency & Intent Ledger
  - Hierarchical 15-Check Final Execution Guard
  - Global Kill Switch Sub-millisecond Safety
  - Feed Circuit Breaker Integration
  - Exact Decimal Quantization
"""
import pytest
import time
from decimal import Decimal
import uuid

from app.signals.safety.kill_switch import kill_switch
from app.signals.safety.feed_circuit import feed_circuit
from app.signals.safety.decimal_types import (
    D,
    Price,
    Quantity,
    normalize_price_to_tick,
    validate_quantity,
)
from app.signals.safety.execution_guard import (
    final_execution_guard,
    GuardCheckResult,
)
from app.signals.execution_intent import (
    make_execution_intent_id,
    make_fyers_order_tag,
    ExecutionIntent,
    IntentState,
    intent_ledger,
)
from app.signals.position import (
    Position,
    PositionState,
    position_registry,
)
from app.signals.fsm import SignalInstance, signal_fsm


@pytest.fixture(autouse=True)
def reset_safety_and_ledgers():
    """Ensure clean global state before each test."""
    kill_switch.deactivate()
    for u in ["NIFTY", "BANKNIFTY", "SENSEX", "TEST"]:
        feed_circuit.on_authoritative_snapshot(u, int(time.time() * 1000), 100)
    intent_ledger.clear()
    position_registry.clear()
    yield
    kill_switch.deactivate()


# ── 1. DETERMINISTIC IDEMPOTENCY & INTENT LEDGER TESTS ────────────────

def test_deterministic_intent_id_hashing():
    sig_id = "sig-12345"
    id_1 = make_execution_intent_id(sig_id, 1, "BUY_TO_OPEN", "", 1)
    id_2 = make_execution_intent_id(sig_id, 1, "BUY_TO_OPEN", "", 1)
    # Must be deterministic across calls
    assert id_1 == id_2
    assert len(id_1) == 32

    # Different action produces different hash
    id_exit = make_execution_intent_id(sig_id, 1, "SELL_TO_CLOSE", "", 1)
    assert id_1 != id_exit

    # Different version produces different hash
    id_v2 = make_execution_intent_id(sig_id, 2, "BUY_TO_OPEN", "", 1)
    assert id_1 != id_v2


def test_fyers_order_tag_format():
    intent_id = make_execution_intent_id("test-sig", 1, "BUY", "", 1)
    tag = make_fyers_order_tag(intent_id)
    assert tag.startswith("DRD_")
    assert len(tag) <= 30


def test_intent_ledger_rejects_duplicates():
    intent_id = make_execution_intent_id("test-sig-dup", 1, "BUY", "", 1)
    intent = ExecutionIntent(
        execution_intent_id=intent_id,
        signal_id="test-sig-dup",
        state=IntentState.CREATED,
        intended_quantity=75,
    )
    reg_intent, is_dup = intent_ledger.register(intent)
    assert not is_dup
    assert reg_intent.execution_intent_id == intent_id

    # Second registration with same ID must flag duplicate
    duplicate_intent = ExecutionIntent(
        execution_intent_id=intent_id,
        signal_id="test-sig-dup",
        state=IntentState.GUARD_PASSED,
        intended_quantity=75,
    )
    reg_dup, is_dup2 = intent_ledger.register(duplicate_intent)
    assert is_dup2
    # State remains original
    assert reg_dup.state == IntentState.CREATED


def test_intent_state_transitions():
    intent_id = make_execution_intent_id("intent-fsm", 1, "BUY", "", 1)
    intent = ExecutionIntent(
        execution_intent_id=intent_id,
        signal_id="sig-fsm",
        state=IntentState.CREATED,
    )
    # Valid transition
    assert intent.transition_to(IntentState.GUARD_PASSED, reason="Guard passed")
    assert intent.state == IntentState.GUARD_PASSED

    assert intent.transition_to(IntentState.SUBMITTED, reason="Sent to broker")
    assert intent.state == IntentState.SUBMITTED

    assert intent.transition_to(IntentState.FILLED, reason="Fill received")
    assert intent.state == IntentState.FILLED

    # Illegal transition from terminal state
    assert not intent.transition_to(IntentState.GUARD_PASSED, reason="Illegal backtrack")
    assert intent.state == IntentState.FILLED


# ── 2. POSITION FSM & DOMAIN SEPARATION TESTS ─────────────────────────

def test_position_fsm_lifecycle():
    pos = Position(
        signal_id="sig-pos-1",
        execution_intent_id="intent-1",
        underlying="NIFTY",
        instrument_symbol="NSE:NIFTY26SEP24800CE",
        entry_price=Decimal("120.50"),
        entry_quantity=75,
        remaining_quantity=75,
    )
    position_registry.register(pos)
    assert pos.position_state == PositionState.OPEN

    # Staged partial exit at T1
    assert pos.transition_to(PositionState.T1_PARTIAL_EXIT, reason="T1 hit", fill_price=Decimal("150.00"))
    assert pos.position_state == PositionState.T1_PARTIAL_EXIT

    # Final runner exit at T2
    assert pos.transition_to(PositionState.T2_EXIT, reason="T2 hit", fill_price=Decimal("180.00"))
    # Auto-finalizes to CLOSED
    assert pos.position_state == PositionState.CLOSED
    assert pos.closed_at_utc is not None
    assert len(pos.history) >= 2


# ── 3. HIERARCHICAL 15-CHECK EXECUTION GUARD TESTS ────────────────────

def _make_dummy_signal(state="ARMED", expired=False):
    now_ms = int(time.time() * 1000)
    sig = SignalInstance(
        signal_id="guard-test-sig",
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("24800.00"),
        entry_min=Decimal("24790.00"),
        entry_max=Decimal("24810.00"),
        trigger=Decimal("24800.00"),
        stop_loss=Decimal("24750.00"),
        target_1=Decimal("24875.00"),
        target_2=Decimal("24950.00"),
        risk_points=Decimal("50.00"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        fsm_state=state,
        option_contract={
            "broker_symbol": "NSE:NIFTY26SEP24800CE",
            "strike": 24800.0,
            "option_type": "CE",
            "lot_size": 75,
            "tick_size": "0.05",
            "min_order_qty": "75",
            "quantity_step": "75",
        },
        expires_at_utc=now_ms - 1000 if expired else now_ms + 300000,
    )
    return sig


def test_guard_level1_kill_switch():
    sig = _make_dummy_signal()
    kill_switch.activate("Operator panic stop")
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "1_KILL_SWITCH"
    assert res.level == 1


def test_guard_level1_ttl_expired():
    sig = _make_dummy_signal(expired=True)
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "2_TTL_VALIDITY"
    assert res.level == 1


def test_guard_level1_market_closed():
    sig = _make_dummy_signal()
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        market_session_state="CLOSED",
        allow_closed_market=False,
    )
    assert not res.passed
    assert res.failed_check == "3_MARKET_SESSION"


def test_guard_level1_non_actionable_state():
    sig = _make_dummy_signal(state="INVALIDATED")
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "4_SIGNAL_ACTIONABLE"


def test_guard_level2_tick_alignment():
    sig = _make_dummy_signal()
    # 120.03 is not aligned to tick size 0.05
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.03"),
        order_quantity=75,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "7_PRICE_TICK_ALIGNMENT"
    assert res.level == 2


def test_guard_level2_quantity_lot_step():
    sig = _make_dummy_signal()
    # 80 is not a multiple of lot size 75
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.05"),
        order_quantity=80,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "8_QUANTITY_STEP_VALIDATION"
    assert res.level == 2


def test_guard_level2_slippage():
    sig = _make_dummy_signal()
    # 122.00 vs 120.00 is ~1.67% slippage, above 0.5% default
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        latest_price=Decimal("122.00"),
        max_slippage_pct=0.5,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "9_SLIPPAGE_POLICY"


def test_guard_level3_feed_degraded():
    sig = _make_dummy_signal()
    feed_circuit.trip("NIFTY", anomaly="OUT_OF_ORDER", reason="Sequence regression")
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "10_FEED_HEALTH"
    assert res.level == 3


def test_guard_level3_clock_drift():
    sig = _make_dummy_signal()
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        clock_drift_ms=2500.0,
        max_clock_drift_ms=2000.0,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "11_CLOCK_DRIFT"


def test_guard_level3_duplicate_order():
    sig = _make_dummy_signal()
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        has_duplicate_order=True,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "14_DUPLICATE_ORDER_GUARD"


def test_guard_level4_persistence_unavailable():
    sig = _make_dummy_signal()
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.00"),
        order_quantity=75,
        audit_available=False,
        allow_closed_market=True,
    )
    assert not res.passed
    assert res.failed_check == "15_PERSISTENCE_DURABILITY"
    assert res.level == 4


def test_guard_all_15_checks_pass():
    sig = _make_dummy_signal()
    res = final_execution_guard(
        signal=sig,
        execution_intent_id="intent-1",
        order_price=Decimal("120.05"),
        order_quantity=75,
        latest_price=Decimal("120.10"),
        feed_health="HEALTHY",
        market_session_state="OPEN",
        contract_spec=sig.option_contract,
        max_slippage_pct=0.5,
        risk_approved=True,
        clock_drift_ms=15.0,
        allow_closed_market=True,
    )
    assert res.passed
    assert res.failed_check is None
    assert len(res.checks_evaluated) == 15


# ── 4. SIGNAL INSTANCE SERIALIZATION & REPRODUCIBILITY ────────────────

def test_signal_instance_serialization():
    sig = _make_dummy_signal()
    sig.execution_intent_id = "intent-xyz"
    sig.position_id = "pos-123"

    audit_d = sig.to_audit_dict()
    assert audit_d["signal_id"] == "guard-test-sig"
    assert audit_d["execution_intent_id"] == "intent-xyz"
    assert audit_d["position_id"] == "pos-123"

    res_d = sig.to_research_dict()
    assert res_d["underlying"] == "NIFTY"
    assert res_d["strategy_version"] == 1
