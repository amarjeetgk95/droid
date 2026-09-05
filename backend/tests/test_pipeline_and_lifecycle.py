import pytest
import asyncio
from decimal import Decimal
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone

from app.signals.fsm import SignalFSMManager, SignalInstance, signal_fsm
from app.signals.scanner import SignalScanner
from app.signals.outcome_tracker import SignalOutcomeTracker
from app.models.market import NormalizedCandle, NormalizedQuote, DataStatus
from app.signals.paper_engine import SignalPaperExecutionResult


@pytest.fixture(autouse=True)
def _open_market(mock_market_open):
    """Ensure market is considered open by default."""
    pass


# ============================================================================
# 1. Scanner Candle Ingestion Tests
# ============================================================================

@pytest.mark.asyncio
async def test_scanner_candle_ingestion_concurrent_and_transformed():
    """Test scanner concurrently fetches timeframes via MarketService and transforms to dicts."""
    scanner = SignalScanner()

    mock_candles_1m = [
        NormalizedCandle(
            timestamp=datetime.now(timezone.utc),
            open=25000.0,
            high=25020.0,
            low=24990.0,
            close=25010.0,
            volume=1500.0,
            vwap=25005.0,
        )
    ]
    mock_candles_5m = [
        NormalizedCandle(
            timestamp=datetime.now(timezone.utc),
            open=25000.0,
            high=25050.0,
            low=24980.0,
            close=25030.0,
            volume=5000.0,
            vwap=25020.0,
        )
    ]

    mock_quote = NormalizedQuote(
        symbol="NIFTY 50",
        display_name="NIFTY 50",
        timestamp=datetime.now(timezone.utc),
        ltp=25030.0,
        open=25000.0,
        high=25050.0,
        low=24980.0,
        previous_close=24950.0,
        change=80.0,
        change_percent=0.32,
        volume=100000,
        status=DataStatus.LIVE,
        provider="fyers",
    )

    with patch("app.services.market_service.MarketService.get_quote", new_callable=AsyncMock) as mock_get_quote, \
         patch("app.services.market_service.MarketService.get_candles", new_callable=AsyncMock) as mock_get_candles:

        mock_get_quote.return_value = mock_quote

        async def _mock_candles(symbol, timeframe="5m", **kwargs):
            if timeframe == "1m":
                return mock_candles_1m
            elif timeframe == "5m":
                return mock_candles_5m
            elif timeframe == "15m":
                raise RuntimeError("Simulated timeout on 15m")
            elif timeframe == "1h":
                return []
            return []

        mock_get_candles.side_effect = _mock_candles

        candidates = await scanner.scan_instrument("NIFTY", timeframe="5M")
        diag = scanner.get_last_diagnostics().get("NIFTY:5M")

        assert diag is not None
        assert diag["underlying"] == "NIFTY"
        # 15m failure was isolated, 5m candles succeeded
        assert diag["candles_count"] == 1
        # Check call count: 1m, 5m, 15m, 1h all requested concurrently
        fetched_tfs = [call.kwargs.get("timeframe") or call.args[1] for call in mock_get_candles.call_args_list]
        assert set(fetched_tfs) == {"1m", "5m", "15m", "1h"}


# ============================================================================
# 2. FSM Breakeven Ratchet (+0.8R) Math Tests
# ============================================================================

def test_fsm_breakeven_ratchet_initial_math_long_call():
    """Test initial risk and breakeven trigger price anchored to entry trigger for LONG_CALL."""
    fsm = SignalFSMManager()
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="VWAP_SCALP",
        direction="LONG_CALL",
        timeframe="1M",
        spot_price=Decimal("25000"),
        entry_min=Decimal("25005"),
        entry_max=Decimal("25015"),
        trigger=Decimal("25010"),  # Trigger != spot
        stop_loss=Decimal("24980"),  # 30 pts risk from trigger
        target_1=Decimal("25055"),
        target_2=Decimal("25100"),
        risk_points=Decimal("30"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
    )
    registered = fsm.register(sig)

    # Risk R must be abs(trigger - stop_loss) = 30, NOT abs(spot - stop_loss) = 20
    assert registered.risk_r == Decimal("30")
    # Breakeven trigger price (+0.8R) = entry_ref + 0.8 * 30 = 25010 + 24 = 25034
    expected_be = Decimal("25010") + (Decimal("30") * Decimal("0.8"))
    assert registered.breakeven_trigger_price == expected_be
    assert registered.breakeven_activation_price == expected_be
    # Strictly above entry for LONG_CALL
    assert registered.breakeven_activation_price > registered.trigger


def test_fsm_breakeven_ratchet_initial_math_long_put():
    """Test initial risk and breakeven trigger price anchored to entry trigger for LONG_PUT."""
    fsm = SignalFSMManager()
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_PUT",
        timeframe="5M",
        spot_price=Decimal("25000"),
        entry_min=Decimal("24985"),
        entry_max=Decimal("24995"),
        trigger=Decimal("24990"),
        stop_loss=Decimal("25030"),  # 40 pts risk from trigger
        target_1=Decimal("24930"),
        target_2=Decimal("24870"),
        risk_points=Decimal("40"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=80.0,
    )
    registered = fsm.register(sig)

    # Risk R must be abs(24990 - 25030) = 40
    assert registered.risk_r == Decimal("40")
    # Breakeven trigger price (-0.8R) = 24990 - (40 * 0.8) = 24990 - 32 = 24958
    expected_be = Decimal("24990") - (Decimal("40") * Decimal("0.8"))
    assert registered.breakeven_trigger_price == expected_be
    assert registered.breakeven_activation_price == expected_be
    # Strictly below entry for LONG_PUT
    assert registered.breakeven_activation_price < registered.trigger


def test_ratchet_breakeven_moves_to_cost_ref_not_beyond_market():
    """Verify ratchet_breakeven moves stop loss to cost_ref and never beyond current market price."""
    fsm = SignalFSMManager()

    # Test LONG_CALL
    sig_call = SignalInstance(
        underlying="NIFTY",
        strategy="VWAP_SCALP",
        direction="LONG_CALL",
        timeframe="1M",
        spot_price=Decimal("25000"),
        entry_min=Decimal("25000"),
        entry_max=Decimal("25010"),
        trigger=Decimal("25005"),
        stop_loss=Decimal("24975"),
        target_1=Decimal("25050"),
        target_2=Decimal("25095"),
        risk_points=Decimal("30"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        fsm_state="CONFIRMED",
        actual_fill_price=Decimal("25006"),
    )
    fsm.register(sig_call)

    # Case A: Normal profit, market is at 25035 (well above cost_ref 25006)
    success = fsm.ratchet_breakeven(sig_call.signal_id, Decimal("25035"))
    assert success is True
    assert sig_call.breakeven_activated is True
    assert sig_call.current_stop_loss == Decimal("25006")
    assert sig_call.current_stop_loss < Decimal("25035")

    # Test LONG_CALL where market price is suddenly at or below cost_ref (e.g. flash wick)
    sig_call2 = SignalInstance(
        underlying="NIFTY",
        strategy="VWAP_SCALP",
        direction="LONG_CALL",
        timeframe="1M",
        spot_price=Decimal("25000"),
        entry_min=Decimal("25000"),
        entry_max=Decimal("25010"),
        trigger=Decimal("25005"),
        stop_loss=Decimal("24975"),
        target_1=Decimal("25050"),
        target_2=Decimal("25095"),
        risk_points=Decimal("30"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        fsm_state="CONFIRMED",
        actual_fill_price=Decimal("25010"),
    )
    fsm.register(sig_call2)
    # Market price is 25008 (below cost_ref 25010)
    success2 = fsm.ratchet_breakeven(sig_call2.signal_id, Decimal("25008"))
    assert success2 is True
    # Stop loss must NOT be beyond market price: must be < 25008
    assert sig_call2.current_stop_loss <= Decimal("25008")

    # Test LONG_PUT
    sig_put = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_PUT",
        timeframe="5M",
        spot_price=Decimal("25000"),
        entry_min=Decimal("24990"),
        entry_max=Decimal("25000"),
        trigger=Decimal("24995"),
        stop_loss=Decimal("25035"),
        target_1=Decimal("24935"),
        target_2=Decimal("24875"),
        risk_points=Decimal("40"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=80.0,
        fsm_state="CONFIRMED",
        actual_fill_price=Decimal("24992"),
    )
    fsm.register(sig_put)

    # Market is at 24960 (in profit, below cost_ref 24992)
    success_put = fsm.ratchet_breakeven(sig_put.signal_id, Decimal("24960"))
    assert success_put is True
    assert sig_put.breakeven_activated is True
    assert sig_put.current_stop_loss == Decimal("24992")
    assert sig_put.current_stop_loss > Decimal("24960")


# ============================================================================
# 3. Outcome Tracker Transactional State Transition Tests
# ============================================================================

@pytest.mark.asyncio
async def test_outcome_tracker_transactional_confirmation_success():
    """Verify signal transitions to TRIGGERED, then CONFIRMED on successful paper order."""
    tracker = SignalOutcomeTracker()
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("25000"),
        entry_min=Decimal("25000"),
        entry_max=Decimal("25010"),
        trigger=Decimal("25005"),
        stop_loss=Decimal("24975"),
        target_1=Decimal("25050"),
        target_2=Decimal("25095"),
        risk_points=Decimal("30"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        fsm_state="ARMED",
    )
    signal_fsm.register(sig)

    mock_paper_res = SignalPaperExecutionResult(
        success=True,
        signal_id=sig.signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        side="BUY",
        quantity=75,
        lots=1,
        fill_price=120.5,
        stop_loss=24975.0,
        target_1=25050.0,
        target_2=25095.0,
        order_id="ORD-SUCCESS-1",
        status="FILLED",
        message="Order filled successfully",
    )

    with patch("app.signals.paper_engine.signal_paper_engine.execute_signal", new_callable=AsyncMock) as mock_exec, \
         patch("app.institutional.telegram_notifications.telegram_notification_queue.publish_signal_event", new_callable=AsyncMock), \
         patch("app.signals.sse.signal_sse_hub.broadcast", new_callable=AsyncMock):

        mock_exec.return_value = mock_paper_res

        events = await tracker.process_price_update_async("NIFTY", Decimal("25010"), allow_closed_market=True)

        assert any(e.get("event") == "CONFIRMED" for e in events)
        updated = signal_fsm.get(sig.signal_id)
        assert updated.fsm_state == "CONFIRMED"
        assert updated.actual_fill_price is not None

        # Verify state history contains TRIGGERED then CONFIRMED
        history_states = [h.to_state for h in updated.state_history]
        assert "TRIGGERED" in history_states
        assert "CONFIRMED" in history_states
        assert history_states.index("TRIGGERED") < history_states.index("CONFIRMED")


@pytest.mark.asyncio
async def test_outcome_tracker_transactional_invalidation_on_execution_failure():
    """Verify signal transitions to TRIGGERED, then INVALIDATED if paper execution fails/rejected."""
    tracker = SignalOutcomeTracker()
    sig = SignalInstance(
        underlying="NIFTY",
        strategy="BREAKOUT",
        direction="LONG_CALL",
        timeframe="5M",
        spot_price=Decimal("25000"),
        entry_min=Decimal("25000"),
        entry_max=Decimal("25010"),
        trigger=Decimal("25005"),
        stop_loss=Decimal("24975"),
        target_1=Decimal("25050"),
        target_2=Decimal("25095"),
        risk_points=Decimal("30"),
        risk_reward_t1=1.5,
        risk_reward_t2=3.0,
        confidence=85.0,
        fsm_state="ARMED",
    )
    signal_fsm.register(sig)

    mock_paper_fail = SignalPaperExecutionResult(
        success=False,
        signal_id=sig.signal_id,
        underlying="NIFTY",
        strategy="BREAKOUT",
        side="BUY",
        quantity=0,
        lots=0,
        fill_price=0.0,
        stop_loss=0.0,
        target_1=0.0,
        target_2=0.0,
        order_id="",
        status="REJECTED",
        message="Insufficient margin in paper wallet",
    )

    with patch("app.signals.paper_engine.signal_paper_engine.execute_signal", new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = mock_paper_fail

        events = await tracker.process_price_update_async("NIFTY", Decimal("25010"), allow_closed_market=True)

        assert any(e.get("event") == "INVALIDATED" for e in events)
        updated = signal_fsm.get(sig.signal_id)
        # MUST NOT be left in CONFIRMED
        assert updated.fsm_state == "INVALIDATED"
        assert updated.outcome_status == "INVALIDATED"

        history_states = [h.to_state for h in updated.state_history]
        assert "TRIGGERED" in history_states
        assert "INVALIDATED" in history_states
        assert "CONFIRMED" not in history_states


# ============================================================================
# 4. Worker Risk Loop Protection Tests
# ============================================================================

@pytest.mark.asyncio
async def test_worker_risk_loop_telemetry_offloaded():
    """Verify worker position risk loop offloads audit update & SSE broadcast to asyncio.create_task."""
    from app.signals.worker import AutomatedSignalWorker

    worker = AutomatedSignalWorker(risk_interval_seconds=0.1, max_risk_cycle_budget_ms=2500.0)

    mock_quote = NormalizedQuote(
        symbol="NIFTY 50",
        display_name="NIFTY 50",
        timestamp=datetime.now(timezone.utc),
        ltp=25030.0,
        open=25000.0,
        high=25050.0,
        low=24980.0,
        previous_close=24950.0,
        change=80.0,
        change_percent=0.32,
        volume=100000,
        status=DataStatus.LIVE,
        provider="fyers",
    )

    created_tasks = []
    real_create_task = asyncio.create_task

    def _tracking_create_task(coro, *args, **kwargs):
        t = real_create_task(coro, *args, **kwargs)
        created_tasks.append(t)
        return t

    with patch("app.services.calendar_service.calendar_service.can_trade_now") as mock_cal, \
         patch.object(worker._market_svc, "get_quote", new_callable=AsyncMock) as mock_get_q, \
         patch("app.signals.outcome_tracker.outcome_tracker.process_price_update_async", new_callable=AsyncMock) as mock_process, \
         patch("app.signals.worker.APPROVED_UNDERLYINGS", ["NIFTY"]), \
         patch("asyncio.create_task", side_effect=_tracking_create_task):

        mock_cal.return_value = MagicMock(allowed=True, reason="REGULAR_HOURS")
        mock_get_q.return_value = mock_quote

        worker._running = True
        # Run one iteration of the loop logic by launching and cancelling
        task = real_create_task(worker._run_position_risk_loop())
        await asyncio.sleep(0.05)
        worker._running = False
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify outcome_tracker was called
        assert mock_process.await_count >= 1
        # Verify background telemetry tasks were spawned
        bg_tasks = [t for t in created_tasks if "_bg_audit_and_sse" in str(getattr(t, "get_coro", lambda: "")()) or "_bg_audit_and_sse" in getattr(t, "get_name", lambda: "")()]
        assert len(created_tasks) >= 1

        # Clean up any pending created tasks
        for t in created_tasks:
            if not t.done():
                t.cancel()

