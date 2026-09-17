import pytest
import time
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock

from app.signals.audit_ledger import SignalAuditLedger
from app.signals.option_marks import OptionMark, OptionMarkService, option_mark_registry, CHAIN_LTP
from app.signals.live_contract_cache import LiveStrikeInfo, live_contract_cache
from datetime import date


class TestRealtimePnLAndMarks:
    def setup_method(self):
        option_mark_registry.clear()

    def test_get_open_option_symbols_filters_and_resolves(self):
        ledger = SignalAuditLedger()
        rec1 = ledger.record_signal_created(
            signal_id="SIG-SNX-01",
            underlying="SENSEX",
            strategy="TREND_PULLBACK",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=82000.0,
            trigger=82100.0,
            stop_loss=81900.0,
            target_1=82300.0,
            target_2=82500.0,
            option_contract={
                "broker_symbol": "BSE:SENSEX2691782100CE",
                "strike": 82100.0,
                "option_type": "CE",
                "expiry": "2026-09-17",
                "lot_size": 20,
            },
            status="CONFIRMED",
        )
        ledger.record_paper_executed(
            signal_id="SIG-SNX-01",
            paper_order_id="ORD-01",
            fill_price=319.98,
            quantity=40,
            lots=2,
            side="BUY",
        )

        rec2 = ledger.record_signal_created(
            signal_id="SIG-NFT-02",
            underlying="NIFTY",
            strategy="TREND_PULLBACK",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=25000.0,
            trigger=25050.0,
            stop_loss=24950.0,
            target_1=25150.0,
            target_2=25250.0,
            option_contract={
                "broker_symbol": "NSE:NIFTY2691725050CE",
                "strike": 25050.0,
                "option_type": "CE",
                "expiry": "2026-09-17",
                "lot_size": 75,
            },
            status="CONFIRMED",
        )
        # Closed trade should not be returned
        rec2.status = "CLOSED"

        # Check SENSEX symbols
        snx_syms = ledger.get_open_option_symbols("SENSEX")
        assert "BSE:SENSEX2691782100CE" in snx_syms
        assert "NSE:NIFTY2691725050CE" not in snx_syms

        # Check all symbols
        all_syms = ledger.get_open_option_symbols()
        assert "BSE:SENSEX2691782100CE" in all_syms
        assert "NSE:NIFTY2691725050CE" not in all_syms

    def test_update_live_quote_recalculates_pnl_in_realtime(self):
        ledger = SignalAuditLedger()
        rec = ledger.record_signal_created(
            signal_id="SIG-LIVE-01",
            underlying="SENSEX",
            strategy="TREND_PULLBACK",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=82000.0,
            trigger=82100.0,
            stop_loss=81900.0,
            target_1=82300.0,
            target_2=82500.0,
            option_contract={
                "broker_symbol": "BSE:SENSEX2691782100CE",
                "strike": 82100.0,
                "option_type": "CE",
                "expiry": "2026-09-17",
                "lot_size": 20,
            },
            status="CONFIRMED",
        )
        ledger.record_paper_executed(
            signal_id="SIG-LIVE-01",
            paper_order_id="ORD-LIVE",
            fill_price=319.98,
            quantity=40,
            lots=2,
            side="BUY",
        )

        now_ms = int(time.time() * 1000)
        # 1. Initial tick at entry price
        mark1 = OptionMark(
            broker_symbol="BSE:SENSEX2691782100CE",
            ltp=319.98,
            source=CHAIN_LTP,
            as_of_utc=now_ms,
        )
        option_mark_registry.put(mark1)

        updated1 = ledger.update_live_quote("SENSEX", 82050.0)
        assert len(updated1) == 1
        assert updated1[0].current_price == 319.98
        assert updated1[0].unrealized_pnl_inr == 0.0
        assert updated1[0].economics_unavailable is False

        # 2. Realtime tick: premium increases to 330.00
        mark2 = OptionMark(
            broker_symbol="BSE:SENSEX2691782100CE",
            ltp=330.00,
            source=CHAIN_LTP,
            as_of_utc=now_ms + 3000,
        )
        option_mark_registry.put(mark2)

        updated2 = ledger.update_live_quote("SENSEX", 82100.0)
        assert len(updated2) == 1
        assert updated2[0].current_price == 330.00
        # Expected points = 330.00 - 319.98 = 10.02, PnL = 10.02 * 40 = 400.80
        assert updated2[0].unrealized_pnl_inr == 400.80
        assert updated2[0].total_pnl_inr == 400.80
        assert updated2[0].is_winner is True

        # 3. Realtime tick: premium drops to 310.00
        mark3 = OptionMark(
            broker_symbol="BSE:SENSEX2691782100CE",
            ltp=310.00,
            source=CHAIN_LTP,
            as_of_utc=now_ms + 6000,
        )
        option_mark_registry.put(mark3)

        updated3 = ledger.update_live_quote("SENSEX", 81950.0)
        assert len(updated3) == 1
        assert updated3[0].current_price == 310.00
        # Expected points = 310.00 - 319.98 = -9.98, PnL = -9.98 * 40 = -399.20
        assert updated3[0].unrealized_pnl_inr == -399.20
        assert updated3[0].total_pnl_inr == -399.20
        assert updated3[0].is_winner is False

    def test_triggered_status_included_in_mtm_and_summary(self):
        ledger = SignalAuditLedger()
        rec = ledger.record_signal_created(
            signal_id="SIG-TRIG-01",
            underlying="SENSEX",
            strategy="TREND_PULLBACK",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=82000.0,
            trigger=82100.0,
            stop_loss=81900.0,
            target_1=82300.0,
            target_2=82500.0,
            option_contract={
                "broker_symbol": "BSE:SENSEX2691782100CE",
                "strike": 82100.0,
                "option_type": "CE",
                "expiry": "2026-09-17",
                "lot_size": 20,
            },
            status="TRIGGERED",
        )
        rec.actual_fill_price = 319.98
        rec.status = "TRIGGERED"

        mark = OptionMark(
            broker_symbol="BSE:SENSEX2691782100CE",
            ltp=319.50,
            source=CHAIN_LTP,
            as_of_utc=int(time.time() * 1000),
        )
        option_mark_registry.put(mark)

        updated = ledger.update_live_quote("SENSEX", 82080.0)
        assert len(updated) == 1
        assert updated[0].status == "TRIGGERED"
        assert updated[0].current_price == 319.50
        # (319.50 - 319.98) * 20 = -0.48 * 20 = -9.60
        assert updated[0].unrealized_pnl_inr == -9.60

        summary = ledger.get_summary_metrics()
        assert summary["net_unrealized_pnl_inr"] == -9.60

    def test_register_chain_strike_saves_to_registry(self):
        strike_info = LiveStrikeInfo(
            broker_symbol="BSE:SENSEX2691782000PE",
            underlying="SENSEX",
            expiry_date=date(2026, 9, 17),
            strike=82000,
            option_type="PE",
            bid=150.0,
            ask=152.0,
            ltp=151.0,
            fetched_at_ms=int(time.time() * 1000),
        )
        mark = OptionMarkService().register_chain_strike(strike_info)
        assert mark is not None
        assert mark.price == 151.0

        # Verify it was put into registry
        stored = option_mark_registry.get_usable("BSE:SENSEX2691782000PE")
        assert stored is not None
        assert stored.price == 151.0

    @pytest.mark.asyncio
    async def test_worker_broadcast_refreshes_open_symbols(self):
        from app.signals.worker import AutomatedSignalWorker
        from app.signals.audit_ledger import signal_audit_ledger
        from app.signals.option_marks import option_mark_service

        worker = AutomatedSignalWorker()
        rec = signal_audit_ledger.record_signal_created(
            signal_id="SIG-TEST-BROADCAST-01",
            underlying="SENSEX",
            strategy="TREND_PULLBACK",
            direction="LONG_CALL",
            timeframe="5M",
            spot_price=82000.0,
            trigger=82100.0,
            stop_loss=81900.0,
            target_1=82300.0,
            target_2=82500.0,
            option_contract={
                "broker_symbol": "BSE:SENSEX2691782100CE",
                "strike": 82100.0,
                "option_type": "CE",
                "expiry": "2026-09-17",
                "lot_size": 20,
            },
            status="CONFIRMED",
        )
        signal_audit_ledger.record_paper_executed(
            signal_id="SIG-TEST-BROADCAST-01",
            paper_order_id="ORD-TEST",
            fill_price=319.98,
            quantity=20,
            lots=1,
            side="BUY",
        )

        with patch.object(option_mark_service, "refresh_and_register", new_callable=AsyncMock) as mock_refresh:
            await worker._broadcast_audit_and_sse("SENSEX", Decimal("82050.0"))
            mock_refresh.assert_awaited_once()
            called_syms = mock_refresh.await_args[0][0]
            assert "BSE:SENSEX2691782100CE" in called_syms

        signal_audit_ledger.delete_trade("SIG-TEST-BROADCAST-01")
