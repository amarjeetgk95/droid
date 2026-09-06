import pytest
import time
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from app.signals.audit_ledger import SignalAuditLedger, AuditTradeRecord, signal_audit_ledger
from app.signals.fsm import SignalFSMManager, SignalInstance, signal_fsm
from app.signals.trigger_gate import check_trigger_integrity, min_trigger_gap_pts
from app.signals.paper_engine import SignalPaperEngine
from app.signals.signals_persistence import sanitize_persisted_signals


class TestOptionPnLAndAuditLedger:
    def test_put_option_pnl_is_positive_on_premium_rise(self):
        """Issue 1: PUT options buy at 120 and exit at 180 must yield positive P&L."""
        ledger = SignalAuditLedger()
        rec = ledger.record_signal_created(
            signal_id="SIG-TEST-PUT-01",
            underlying="NIFTY",
            strategy="BREAKDOWN",
            direction="LONG_PUT",
            timeframe="5M",
            spot_price=25000.0,
            trigger=24950.0,
            stop_loss=25020.0,
            target_1=24850.0,
            target_2=24750.0,
            confidence=85.0,
            option_contract={
                "broker_symbol": "NIFTY24DEC24950PE",
                "strike": 24950.0,
                "option_type": "PE",
                "expiry": "2024-12-26",
                "lot_size": 75,
            },
        )
        ledger.record_paper_executed(
            signal_id="SIG-TEST-PUT-01",
            paper_order_id="ORD-001",
            fill_price=120.0,
            quantity=75,
            lots=1,
            side="BUY",
        )

        closed = ledger.record_square_off(
            signal_id="SIG-TEST-PUT-01",
            exit_price=180.0,
            exit_reason="TARGET_1_HIT",
        )
        assert closed is not None
        assert closed.actual_pnl_points == 60.0, f"Expected +60.0 points, got {closed.actual_pnl_points}"
        assert closed.actual_pnl_inr == 4500.0, f"Expected +4500.0 INR, got {closed.actual_pnl_inr}"
        assert closed.is_winner is True
        assert closed.status == "WON"

    def test_call_option_pnl_calculation(self):
        """CALL options buy at 100 and exit at 150 must yield positive P&L."""
        ledger = SignalAuditLedger()
        ledger.record_signal_created(
            signal_id="SIG-TEST-CALL-01",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=25000.0,
            trigger=25050.0,
            stop_loss=24980.0,
            target_1=25150.0,
            target_2=25250.0,
            confidence=85.0,
            option_contract={
                "broker_symbol": "NIFTY24DEC25050CE",
                "strike": 25050.0,
                "option_type": "CE",
                "expiry": "2024-12-26",
                "lot_size": 75,
            },
        )
        ledger.record_paper_executed(
            signal_id="SIG-TEST-CALL-01",
            paper_order_id="ORD-002",
            fill_price=100.0,
            quantity=75,
            lots=1,
            side="BUY",
        )

        closed = ledger.record_square_off(
            signal_id="SIG-TEST-CALL-01",
            exit_price=150.0,
            exit_reason="TARGET_1_HIT",
        )
        assert closed is not None
        assert closed.actual_pnl_points == 50.0
        assert closed.actual_pnl_inr == 3750.0
        assert closed.is_winner is True
        assert closed.status == "WON"

    def test_live_mtm_does_not_mix_spot_and_option_premium(self):
        """Issue 2: Option position MTM must use estimated option price, not spot minus premium."""
        ledger = SignalAuditLedger()
        # 1. Armed record (unexecuted)
        ledger.record_signal_created(
            signal_id="SIG-ARMED-01",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=25000.0,
            trigger=25050.0,
            stop_loss=24980.0,
            target_1=25150.0,
            target_2=25250.0,
        )

        # 2. Executed record
        ledger.record_signal_created(
            signal_id="SIG-EXEC-01",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=25000.0,
            trigger=25050.0,
            stop_loss=24980.0,
            target_1=25150.0,
            target_2=25250.0,
            option_contract={
                "broker_symbol": "NIFTY24DEC25050CE",
                "strike": 25050.0,
                "option_type": "CE",
                "lot_size": 75,
            },
        )
        ledger.record_paper_executed(
            signal_id="SIG-EXEC-01",
            paper_order_id="ORD-003",
            fill_price=150.0,
            quantity=75,
            lots=1,
            side="BUY",
        )

        # Spot advances to 25060
        updated = ledger.update_live_quote("NIFTY", 25060.0)

        armed_rec = ledger.get("SIG-ARMED-01")
        assert armed_rec.unrealized_pnl_inr == 0.0, "Armed trade should have 0.0 unrealized MTM"
        assert armed_rec.unrealized_pnl_points == 0.0

        exec_rec = ledger.get("SIG-EXEC-01")
        # Incommensurable bug would have given: (25060 - 150) * 75 = 1,868,250 INR!
        assert exec_rec.unrealized_pnl_inr is not None
        assert abs(exec_rec.unrealized_pnl_inr) < 50000.0, (
            f"Unrealized P&L is implausibly high ({exec_rec.unrealized_pnl_inr}), spot mixed with premium!"
        )

    def test_option_slippage_calculation_not_astronomical(self):
        """Issue 4: Option fill vs trigger should not compare 150 premium with 25000 spot."""
        ledger = SignalAuditLedger()
        ledger.record_signal_created(
            signal_id="SIG-SLIPPAGE-01",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=25000.0,
            trigger=25050.0,
            stop_loss=24980.0,
            target_1=25150.0,
            target_2=25250.0,
            option_contract={
                "broker_symbol": "NIFTY24DEC25050CE",
                "strike": 25050.0,
                "option_type": "CE",
                "lot_size": 75,
            },
        )
        ledger.record_paper_executed(
            signal_id="SIG-SLIPPAGE-01",
            paper_order_id="ORD-004",
            fill_price=150.0,
            quantity=75,
            lots=1,
        )
        rec = ledger.get("SIG-SLIPPAGE-01")
        assert rec.slippage_points is not None
        assert rec.slippage_points < 100.0, f"Slippage points ({rec.slippage_points}) compares spot with premium!"

    def test_summary_metrics_includes_target_1_hit(self):
        """Issue 10: Runner signals with status TARGET_1_HIT must be counted in open_t."""
        ledger = SignalAuditLedger()
        rec = ledger.record_signal_created(
            signal_id="SIG-RUNNER-01",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=25000.0,
            trigger=25050.0,
            stop_loss=24980.0,
            target_1=25150.0,
            target_2=25250.0,
        )
        ledger.record_state_transition("SIG-RUNNER-01", "TARGET_1_HIT", market_price=25150.0)
        summary = ledger.get_summary_metrics()
        assert summary["open_trades"] == 1


class TestPaperEngineAndLifecycle:
    @pytest.mark.asyncio
    async def test_close_signal_position_optional_exit_price(self):
        """Issue 6: close_signal_position without exit_price must not raise TypeError."""
        engine = SignalPaperEngine()
        sig = SignalInstance(
            signal_id="SIG-DEL-TEST",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("25000"),
            trigger=Decimal("25050"),
            entry_min=Decimal("25045"),
            entry_max=Decimal("25055"),
            stop_loss=Decimal("24980"),
            target_1=Decimal("25150"),
            target_2=Decimal("25250"),
            risk_points=Decimal("70"),
            risk_reward_t1=1.5,
            risk_reward_t2=3.0,
            confidence=85.0,
            paper_order={"symbol": "NIFTY24DEC25050CE", "quantity": 75},
        )
        signal_fsm.register(sig)

        # Calling without exit_price must succeed gracefully
        res = await engine.close_signal_position("SIG-DEL-TEST", reason="DELETED_BY_USER")
        # Successfully executed without raising TypeError

    @pytest.mark.asyncio
    async def test_partial_exit_at_t1_preserves_running_trade(self):
        """Issue 5: T1 partial exit must set TARGET_1_HIT and not prematurely WON the trade."""
        engine = SignalPaperEngine()

        sig = SignalInstance(
            signal_id="SIG-T1-PARTIAL",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("25000"),
            trigger=Decimal("25050"),
            entry_min=Decimal("25045"),
            entry_max=Decimal("25055"),
            stop_loss=Decimal("24980"),
            target_1=Decimal("25150"),
            target_2=Decimal("25250"),
            risk_points=Decimal("70"),
            risk_reward_t1=1.5,
            risk_reward_t2=3.0,
            confidence=85.0,
            paper_order={"symbol": "NIFTY24DEC25050CE", "quantity": 75},
        )
        signal_fsm.register(sig)
        signal_audit_ledger.record_signal_created(
            signal_id="SIG-T1-PARTIAL",
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=25000.0,
            trigger=25050.0,
            stop_loss=24980.0,
            target_1=25150.0,
            target_2=25250.0,
        )
        signal_audit_ledger.record_paper_executed(
            signal_id="SIG-T1-PARTIAL",
            paper_order_id="ORD-PARTIAL",
            fill_price=100.0,
            quantity=75,
            lots=2,
        )

        # Partial close of 37 qty at T1
        res = await engine.close_signal_position(
            "SIG-T1-PARTIAL",
            exit_price=150.0,
            reason="TARGET_1_HIT",
            quantity_to_close=37,
        )
        rec = signal_audit_ledger.get("SIG-T1-PARTIAL")
        assert rec.status == "TARGET_1_HIT", f"Status should be TARGET_1_HIT, got {rec.status}"

        # Later runner exit at T2 closes the remaining position
        res_final = await engine.close_signal_position(
            "SIG-T1-PARTIAL",
            exit_price=200.0,
            reason="TARGET_2_HIT",
            quantity_to_close=38,
        )
        rec_final = signal_audit_ledger.get("SIG-T1-PARTIAL")
        assert rec_final.status == "WON"
        assert rec_final.exit_price == 200.0


class TestScalpTriggerGateAndCorridors:
    def test_scalp_desk_accepts_tight_gap_and_low_risk(self):
        """Issue 8: 1M scalp setups with 3pt gap and 6pt risk must pass the trigger gate."""
        res_scalp = check_trigger_integrity(
            underlying="NIFTY",
            strategy="VWAP_SCALP",
            direction="LONG_CALL",
            spot_price=Decimal("25000.0"),
            entry_min=Decimal("25003.0"),
            entry_max=Decimal("25006.0"),
            trigger=Decimal("25003.0"),
            stop_loss=Decimal("24997.0"),
            target_1=Decimal("25012.0"),
            target_2=Decimal("25021.0"),
            risk_points=Decimal("6.0"),
            is_scalp=True,
            timeframe="1M",
        )
        assert res_scalp.passed is True, f"Scalp should pass trigger gate: {res_scalp.reason_code}: {res_scalp.message}"

        # Contrast with standard intraday 5M gate (should reject tight gap)
        res_intraday = check_trigger_integrity(
            underlying="NIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            spot_price=Decimal("25000.0"),
            entry_min=Decimal("25003.0"),
            entry_max=Decimal("25006.0"),
            trigger=Decimal("25003.0"),
            stop_loss=Decimal("24997.0"),
            target_1=Decimal("25012.0"),
            target_2=Decimal("25021.0"),
            risk_points=Decimal("6.0"),
            is_scalp=False,
            timeframe="5M",
        )
        assert res_intraday.passed is False
        assert res_intraday.reason_code == "TRIGGER_TOO_CLOSE"

    def test_banknifty_plausible_corridor_accepts_real_market_prices(self):
        """Issue 9: Bank Nifty at 49,500 must not be purged by sanitize_persisted_signals."""
        bnf_trade = signal_audit_ledger.record_signal_created(
            signal_id="SIG-REAL-BNF-01",
            underlying="BANKNIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=49500.0,
            trigger=49600.0,
            stop_loss=49400.0,
            target_1=49800.0,
            target_2=50000.0,
        )
        bnf_fsm = SignalInstance(
            signal_id="SIG-REAL-BNF-01",
            underlying="BANKNIFTY",
            strategy="BREAKOUT",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=Decimal("49500.0"),
            trigger=Decimal("49600.0"),
            entry_min=Decimal("49590.0"),
            entry_max=Decimal("49610.0"),
            stop_loss=Decimal("49400.0"),
            target_1=Decimal("49800.0"),
            target_2=Decimal("50000.0"),
            risk_points=Decimal("200.0"),
            risk_reward_t1=1.0,
            risk_reward_t2=2.0,
            confidence=85.0,
        )
        signal_fsm.register(bnf_fsm)

        # Run sanitizer
        sanitize_persisted_signals()

        assert signal_audit_ledger.get("SIG-REAL-BNF-01") is not None, "Real Bank Nifty trade was incorrectly purged!"
        assert signal_fsm.get("SIG-REAL-BNF-01") is not None, "Real Bank Nifty FSM was incorrectly purged!"
