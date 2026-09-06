"""
Unit Tests for Crypto Scalp Outcome Tracker, Paper Execution, and Performance Engine.
Validates deterministic FSM state transitions, T1 partial exits, BE ratchets,
conservative ambiguity handling, time-stops, and statistical metrics attribution.
"""
import pytest
import time
from app.models.crypto import CryptoScalpSignal, SignalDirection, CryptoSignalStatus
from app.crypto_scalp.models_execution import (
    CryptoScalpPositionState,
    CryptoScalpExitEventType,
    CryptoScalpExecutionConfig,
    CryptoScalpExecutionRecord,
)
from app.crypto_scalp.outcome_tracker import CryptoScalpOutcomeTracker
from app.crypto_scalp.performance import CryptoScalpPerformanceEngine


@pytest.fixture
def clean_tracker():
    """Create fresh outcome tracker with zero slippage/fees for baseline validation."""
    config = CryptoScalpExecutionConfig(
        account_equity=10_000.0,
        risk_per_trade_pct=1.0,
        target_1_close_fraction=0.50,
        entry_slippage_bps=0.0,
        exit_slippage_bps=0.0,
        taker_fee_bps=0.0,
        time_stop_seconds=1800,
        ambiguous_trigger_policy="CONSERVATIVE",
    )
    return CryptoScalpOutcomeTracker(config=config)


@pytest.fixture
def sample_long_signal():
    return CryptoScalpSignal(
        id="TEST_LONG_1",
        symbol="BTCUSDT",
        asset="BTC",
        direction=SignalDirection.LONG,
        strategy="VWAP_BOUNCE",
        strategy_name="VWAP Rejection Scalp",
        entry_price=90_000.0,
        stop_loss=89_500.0,  # 500 risk points
        target_1=90_750.0,   # 1.5R (+750)
        target_2=91_250.0,   # 2.5R (+1250)
        current_price=90_000.0,
        risk_points=500.0,
        risk_percent=0.55,
        risk_reward_ratio=1.5,
        confidence=85.0,
        timeframe="1m",
        status=CryptoSignalStatus.ACTIVE,
        rationale="VWAP bounce test setup",
        created_at_utc=1000000,
    )


@pytest.fixture
def sample_short_signal():
    return CryptoScalpSignal(
        id="TEST_SHORT_1",
        symbol="BTCUSDT",
        asset="BTC",
        direction=SignalDirection.SHORT,
        strategy="EMA_CROSS_SCALP",
        strategy_name="Micro EMA Cross Scalp",
        entry_price=90_000.0,
        stop_loss=90_500.0,  # 500 risk points
        target_1=89_250.0,   # 1.5R (-750)
        target_2=88_750.0,   # 2.5R (-1250)
        current_price=90_000.0,
        risk_points=500.0,
        risk_percent=0.55,
        risk_reward_ratio=1.5,
        confidence=82.0,
        timeframe="1m",
        status=CryptoSignalStatus.ACTIVE,
        rationale="EMA cross test setup",
        created_at_utc=1000000,
    )


@pytest.mark.asyncio
async def test_long_t1_partial_exit_and_t2_hit(clean_tracker, sample_long_signal):
    """Test Long trade lifecycle: T1 partial exit (50%), stop ratchet to BE, then T2 full exit."""
    trade = await clean_tracker.register_signal(sample_long_signal)
    assert trade.position_state == CryptoScalpPositionState.ACTIVE
    assert trade.current_stop_price == 89_500.0
    initial_qty = trade.quantity_initial

    # Tick 1: Price rallies to 90,800 (exceeds T1: 90,750)
    transitions = await clean_tracker.process_tick(
        symbol="BTCUSDT",
        current_price=90_800.0,
        high=90_800.0,
        low=90_050.0,
        timestamp_ms=1010000,
    )

    assert len(transitions) == 1
    t = transitions[0]
    assert t.position_state == CryptoScalpPositionState.PARTIALLY_CLOSED
    assert t.quantity_closed_t1 == pytest.approx(initial_qty * 0.5, rel=1e-3)
    assert t.quantity_remaining == pytest.approx(initial_qty * 0.5, rel=1e-3)
    # Stop should be ratcheted to breakeven (entry fill price)
    assert t.current_stop_price == pytest.approx(t.entry_fill_price, rel=1e-3)
    assert t.t1_hit_at == 1010000

    # Tick 2: Price surges to 91,300 (exceeds T2: 91,250)
    transitions2 = await clean_tracker.process_tick(
        symbol="BTCUSDT",
        current_price=91_300.0,
        high=91_300.0,
        low=90_700.0,
        timestamp_ms=1020000,
    )

    assert len(transitions2) == 1
    t_final = transitions2[0]
    assert t_final.position_state == CryptoScalpPositionState.CLOSED
    assert t_final.exit_reason == CryptoScalpExitEventType.T2_HIT
    assert t_final.quantity_remaining == 0.0
    assert t_final.theoretical_r == 2.0
    assert t_final.r_multiple > 0
    assert t_final.duration_seconds == 20  # (1020000 - 1000000) / 1000
    assert t_final.trade_id not in clean_tracker.active_positions


@pytest.mark.asyncio
async def test_long_t1_then_breakeven_stop(clean_tracker, sample_long_signal):
    """Test Long trade reaches T1, ratchets to BE, and subsequently exits at BE stop."""
    trade = await clean_tracker.register_signal(sample_long_signal)

    # 1. Hit T1
    await clean_tracker.process_tick(
        symbol="BTCUSDT",
        current_price=90_800.0,
        high=90_800.0,
        low=90_050.0,
        timestamp_ms=1010000,
    )
    assert trade.position_state == CryptoScalpPositionState.PARTIALLY_CLOSED

    # 2. Pullback drops to entry price (90,000.0)
    transitions = await clean_tracker.process_tick(
        symbol="BTCUSDT",
        current_price=89_950.0,
        high=90_200.0,
        low=89_950.0,
        timestamp_ms=1030000,
    )

    assert len(transitions) == 1
    t = transitions[0]
    assert t.position_state == CryptoScalpPositionState.CLOSED
    assert t.exit_reason == CryptoScalpExitEventType.BREAKEVEN_STOP
    assert t.theoretical_r == 0.75  # 50% at 1.5R + 50% at 0R
    assert t.r_multiple > 0  # Still profitable from the 50% booked at T1!


@pytest.mark.asyncio
async def test_short_initial_stop_loss(clean_tracker, sample_short_signal):
    """Test Short trade immediately hits initial Stop Loss."""
    trade = await clean_tracker.register_signal(sample_short_signal)
    assert trade.position_state == CryptoScalpPositionState.ACTIVE

    # Price pumps up to 90,600 (breaches Short SL at 90,500)
    transitions = await clean_tracker.process_tick(
        symbol="BTCUSDT",
        current_price=90_600.0,
        high=90_600.0,
        low=90_000.0,
        timestamp_ms=1005000,
    )

    assert len(transitions) == 1
    t = transitions[0]
    assert t.position_state == CryptoScalpPositionState.CLOSED
    assert t.exit_reason == CryptoScalpExitEventType.INITIAL_STOP
    assert t.theoretical_r == -1.0
    assert t.r_multiple < 0


@pytest.mark.asyncio
async def test_conservative_ambiguity_handling(clean_tracker, sample_long_signal):
    """If a single tick/bar breaches both Target 1 and Stop Loss, conservatively assume Stop Loss."""
    await clean_tracker.register_signal(sample_long_signal)

    # Volatile bar: High reaches 91,000 (> T1) AND Low plunges to 89,400 (< SL)
    transitions = await clean_tracker.process_tick(
        symbol="BTCUSDT",
        current_price=90_000.0,
        high=91_000.0,
        low=89_400.0,
        timestamp_ms=1005000,
    )

    assert len(transitions) == 1
    t = transitions[0]
    assert t.position_state == CryptoScalpPositionState.CLOSED
    assert t.exit_reason == CryptoScalpExitEventType.INITIAL_STOP
    assert t.theoretical_r == -1.0


@pytest.mark.asyncio
async def test_time_stop_expiration(clean_tracker, sample_long_signal):
    """Trade should exit at market price after 30 minutes (1800 seconds)."""
    await clean_tracker.register_signal(sample_long_signal)

    # 1801 seconds later, price is at 90,200 (between entry and T1)
    transitions = await clean_tracker.process_tick(
        symbol="BTCUSDT",
        current_price=90_200.0,
        high=90_250.0,
        low=90_150.0,
        timestamp_ms=1000000 + (1801 * 1000),
    )

    assert len(transitions) == 1
    t = transitions[0]
    assert t.position_state == CryptoScalpPositionState.CLOSED
    assert t.exit_reason == CryptoScalpExitEventType.TIME_STOP
    assert t.duration_seconds >= 1800


def test_performance_metrics_statistical_gates():
    """Verify performance engine win rate, profit factor, and sample size gate."""
    # Create 5 winning trades and 3 losing trades (Total 8 trades -> insufficient sample)
    records = []
    for i in range(5):
        records.append(CryptoScalpExecutionRecord(
            trade_id=f"t_win_{i}",
            signal_id=f"s_win_{i}",
            symbol="BTCUSDT",
            asset="BTC",
            direction=SignalDirection.LONG,
            strategy="VWAP_BOUNCE",
            strategy_name="VWAP Rejection Scalp",
            position_state=CryptoScalpPositionState.CLOSED,
            signal_price=90_000.0,
            entry_fill_price=90_000.0,
            initial_stop_price=89_500.0,
            current_stop_price=90_000.0,
            target_1_price=90_750.0,
            target_2_price=91_250.0,
            exit_price=91_250.0,
            exit_reason=CryptoScalpExitEventType.T2_HIT,
            quantity_initial=0.2,
            quantity_remaining=0.0,
            initial_risk_usd=100.0,
            net_pnl_usd=200.0,
            r_multiple=2.0,
            theoretical_r=2.0,
            execution_drag_r=0.0,
            duration_seconds=600,
        ))

    for j in range(3):
        records.append(CryptoScalpExecutionRecord(
            trade_id=f"t_loss_{j}",
            signal_id=f"s_loss_{j}",
            symbol="BTCUSDT",
            asset="BTC",
            direction=SignalDirection.SHORT,
            strategy="VWAP_BOUNCE",
            strategy_name="VWAP Rejection Scalp",
            position_state=CryptoScalpPositionState.CLOSED,
            signal_price=90_000.0,
            entry_fill_price=90_000.0,
            initial_stop_price=90_500.0,
            current_stop_price=90_500.0,
            target_1_price=89_250.0,
            target_2_price=88_750.0,
            exit_price=90_500.0,
            exit_reason=CryptoScalpExitEventType.INITIAL_STOP,
            quantity_initial=0.2,
            quantity_remaining=0.0,
            initial_risk_usd=100.0,
            net_pnl_usd=-100.0,
            r_multiple=-1.0,
            theoretical_r=-1.0,
            execution_drag_r=0.0,
            duration_seconds=300,
        ))

    metrics = CryptoScalpPerformanceEngine.calculate_metrics(records)

    assert metrics.completed_trades == 8
    assert metrics.winning_trades == 5
    assert metrics.losing_trades == 3
    assert metrics.win_rate_pct == 62.5  # 5 / 8 = 62.5%
    assert metrics.gross_profit_usd == 1000.0  # 5 * 200
    assert metrics.gross_loss_usd == 300.0    # 3 * 100
    assert metrics.profit_factor == pytest.approx(3.33, rel=1e-2)
    assert metrics.insufficient_sample is True  # Because 8 < 10

    # Now add 2 more trades to reach sample size 10
    records.append(records[0].model_copy(update={"trade_id": "extra_1"}))
    records.append(records[0].model_copy(update={"trade_id": "extra_2"}))

    metrics10 = CryptoScalpPerformanceEngine.calculate_metrics(records)
    assert metrics10.completed_trades == 10
    assert metrics10.insufficient_sample is False
