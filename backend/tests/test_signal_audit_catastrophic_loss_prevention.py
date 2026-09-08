"""
Tests for catastrophic phantom loss prevention, option max loss bounds,
and zero-open-position exposure honesty.
"""
import pytest
from app.signals.audit_ledger import SignalAuditLedger, signal_audit_ledger
from app.signals.signals_persistence import sanitize_persisted_signals


OPT_BNF_CE = {
    "broker_symbol": "NSE:BANKNIFTY26SEP0956800CE",
    "option_type": "CE",
    "strike": 56800.0,
    "lot_size": 30,
}


def test_square_off_with_spot_fill_price_reconciles_and_bounds_loss():
    """
    Simulates the exact production bug:
    Spot level (56816.69) was logged as actual_fill_price for a BANKNIFTY 56800 CE option,
    and square-off occurred at 283.38.
    Previously produced: -16,95,999.30 INR.
    Must now produce: sensible PnL bounded by realistic entry premium.
    """
    ledger = SignalAuditLedger()
    ledger.record_signal_created(
        signal_id="SIG-BNF-BUG-1",
        underlying="BANKNIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=56816.69,
        trigger=56816.69,
        stop_loss=56700.0,
        target_1=57000.0,
        target_2=57200.0,
        option_contract=dict(OPT_BNF_CE),
        lots=1,
        status="CONFIRMED",
    )
    # Polluted fill price with spot
    ledger.record_paper_executed(
        signal_id="SIG-BNF-BUG-1",
        paper_order_id="ORD-BUG-1",
        fill_price=56816.69,
        quantity=30,
        lots=1,
        side="BUY",
    )

    # Square off at option premium 283.38
    rec = ledger.record_square_off(
        signal_id="SIG-BNF-BUG-1",
        exit_price=283.38,
        exit_reason="STOP_LOSS_HIT",
    )

    assert rec is not None
    # Entry price must have been reconciled from 56816.69 to option premium (< 1000)
    assert rec.actual_fill_price < 2000.0
    # Loss must never be anywhere near -16 lakhs!
    assert abs(rec.actual_pnl_inr) < 20000.0
    # Loss for option buyer is bounded by entry_price * qty
    assert rec.actual_pnl_inr >= -1.0 * rec.actual_fill_price * 30


def test_option_buying_loss_never_exceeds_100_percent():
    """
    Option buyer paying 150 premium for 75 qty can lose at most 150 * 75 = 11,250 INR,
    even if exit_price is 0 or negative.
    """
    ledger = SignalAuditLedger()
    ledger.record_signal_created(
        signal_id="SIG-BUY-OPT-1",
        underlying="NIFTY",
        strategy="TREND_PULLBACK",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=25000.0,
        trigger=25000.0,
        stop_loss=24950.0,
        target_1=25100.0,
        target_2=25200.0,
        option_contract={"broker_symbol": "NSE:NIFTY26SEP25000CE", "option_type": "CE", "strike": 25000.0, "lot_size": 75},
        lots=1,
        status="CONFIRMED",
    )
    ledger.record_paper_executed(
        signal_id="SIG-BUY-OPT-1",
        paper_order_id="ORD-EXP-1",
        fill_price=150.0,
        quantity=75,
        lots=1,
        side="BUY",
    )
    rec = ledger.record_square_off(
        signal_id="SIG-BUY-OPT-1",
        exit_price=0.05,
        exit_reason="EXPIRED",
    )
    assert rec.actual_pnl_inr >= -11250.0
    assert rec.actual_pnl_pct >= -100.0


def test_summary_exposure_is_zero_when_no_open_positions():
    """
    When all trades are closed or only ARMED/CONFIRMED signals exist,
    total_active_exposure_inr MUST be 0.0.
    """
    ledger = SignalAuditLedger()
    # ARMED signal (no order placed yet)
    ledger.record_signal_created(
        signal_id="SIG-ARMED-1",
        underlying="BANKNIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=56800.0,
        trigger=56850.0,
        stop_loss=56700.0,
        target_1=57000.0,
        target_2=57200.0,
        option_contract=dict(OPT_BNF_CE),
        lots=1,
        status="ARMED",
    )
    # CONFIRMED signal (waiting for execution)
    ledger.record_signal_created(
        signal_id="SIG-CONFIRMED-1",
        underlying="NIFTY",
        strategy="MOMENTUM",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=25000.0,
        trigger=25020.0,
        stop_loss=24980.0,
        target_1=25100.0,
        target_2=25200.0,
        option_contract={"broker_symbol": "NSE:NIFTY26SEP25000CE", "option_type": "CE", "strike": 25000.0, "lot_size": 75},
        lots=1,
        status="CONFIRMED",
    )

    metrics = ledger.get_summary_metrics()
    # Since neither signal is EXECUTED, active exposure must be exactly 0.0!
    assert metrics["total_active_exposure_inr"] == 0.0


def test_sanitize_persisted_signals_repairs_corrupted_row():
    """
    Verify sanitize_persisted_signals repairs any row with catastrophic PnL or spot fill price.
    """
    corrupt_id = "SIG-CORRUPT-TEST-1"
    rec = signal_audit_ledger.record_signal_created(
        signal_id=corrupt_id,
        underlying="BANKNIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=56816.69,
        trigger=56816.69,
        stop_loss=56700.0,
        target_1=57000.0,
        target_2=57200.0,
        option_contract=dict(OPT_BNF_CE),
        lots=1,
        status="EXECUTED",
    )
    rec.actual_fill_price = 56816.69
    rec.exit_price = 283.38
    rec.actual_pnl_inr = -1695999.30
    rec.actual_pnl_points = -56533.31
    rec.status = "LOST"

    try:
        sanitize_persisted_signals()
        repaired = signal_audit_ledger.get(corrupt_id)
        assert repaired is not None
        assert repaired.actual_fill_price < 2000.0
        assert repaired.actual_pnl_inr > -20000.0
    finally:
        signal_audit_ledger.delete_trade(corrupt_id)
