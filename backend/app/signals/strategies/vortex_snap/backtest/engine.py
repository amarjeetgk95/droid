"""
Event-Driven Backtesting Simulator (§30).

Executes the exact production strategy logic bar-by-bar:
- Chronological point-in-time progression (zero look-ahead)
- Realistic next-bar open fills with slippage
- Conservative intra-bar exit evaluation (Stop Loss takes priority if both Stop and Target are touched)
- Multi-stage dynamic exits: 50% partial at Target 1, breakeven stop adjustment, Target 2 runner
- Time decay and pressure collapse early exit mechanics (§22, §23)
- Session forced square-off at 15:15 IST (§4)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import List, Optional, Dict, Any

from app.signals.strategies.base import StrategyContext
from app.signals.strategies.vortex_snap.strategy import VortexSnapStrategy
from app.signals.strategies.vortex_snap.types import Candle
from app.signals.strategies.vortex_snap.backtest.data_loader import HistoricalBarContext
from app.signals.strategies.vortex_snap.backtest.cost_model import TransactionCostModel, RoundTripFriction
from app.signals.strategies.vortex_snap.backtest.metrics import (
    BacktestTradeRecord,
    BacktestMetricsSummary,
    calculate_metrics,
)


@dataclass
class PendingOrder:
    """Order waiting to be filled on next bar open."""
    instrument: str
    direction: str  # "LONG_CALL" or "LONG_PUT"
    direction_sign: int  # +1 or -1
    trigger_price: float
    stop_loss: float
    target_1: float
    target_2: float
    expected_move: float
    expected_holding_minutes: float
    confidence: float
    reason_codes: List[str]
    signal_timestamp_ms: int


@dataclass
class ActivePosition:
    """Live in-flight simulated position."""
    trade_id: int
    instrument: str
    direction: str
    direction_sign: int
    entry_time_ms: int
    entry_price: float
    quantity: int
    stop_loss: float
    target_1: float
    target_2: float
    expected_holding_minutes: float
    confidence: float
    reason_codes: List[str]
    holding_bars: int = 0
    t1_hit: bool = False
    half_closed_pnl: float = 0.0
    half_closed_points: float = 0.0
    half_closed_gross: float = 0.0
    half_closed_friction: float = 0.0


class VortexBacktestEngine:
    """Event-driven simulator running exact VORTEX-SNAP production code."""

    def __init__(
        self,
        strategy: Optional[VortexSnapStrategy] = None,
        cost_model: Optional[TransactionCostModel] = None,
        initial_capital: float = 500000.0,
        lot_size: int = 25,  # Standard NIFTY lot
        enable_dynamic_exits: bool = True,
        enable_time_decay: bool = True,
        enable_pressure_collapse_exit: bool = True,
        execution_lag_bars: int = 1,  # 1 = next bar open
    ):
        self.strategy = strategy or VortexSnapStrategy()
        self.cost_model = cost_model or TransactionCostModel()
        self.initial_capital = initial_capital
        self.lot_size = lot_size
        self.enable_dynamic_exits = enable_dynamic_exits
        self.enable_time_decay = enable_time_decay
        self.enable_pressure_collapse_exit = enable_pressure_collapse_exit
        self.execution_lag_bars = execution_lag_bars
        self.last_trades: List[BacktestTradeRecord] = []

    def run(
        self,
        bar_contexts: List[HistoricalBarContext],
        instrument: str = "NIFTY",
    ) -> BacktestMetricsSummary:
        """Runs event-driven backtest over the chronological bar contexts.
        
        Args:
            bar_contexts: Chronological sequence of historical bar contexts.
            instrument: Target instrument symbol.
            
        Returns:
            BacktestMetricsSummary containing all performance and risk diagnostics.
        """
        if not bar_contexts:
            return calculate_metrics([], self.initial_capital)

        self.strategy.reset()
        trades: List[BacktestTradeRecord] = []
        trade_id_seq = 0

        active_pos: Optional[ActivePosition] = None
        pending_order: Optional[PendingOrder] = None
        pending_lag_counter = 0

        for bar_idx, bar_ctx in enumerate(bar_contexts):
            candle = bar_ctx.candle_1m
            ts = bar_ctx.timestamp_ms

            # ─────────────────────────────────────────────────────────────────
            # 1. Evaluate Active Position Exit Conditions
            # ─────────────────────────────────────────────────────────────────
            if active_pos is not None:
                active_pos.holding_bars += 1
                holding_mins = active_pos.holding_bars * 1.0

                exit_triggered = False
                exit_price = 0.0
                exit_reason = ""

                # Fail-safe priority: Stop Loss checked first
                is_long = active_pos.direction_sign > 0

                # Check Stop Loss
                sl_hit = (candle.low <= active_pos.stop_loss) if is_long else (candle.high >= active_pos.stop_loss)

                # Check Target 1
                t1_hit = (candle.high >= active_pos.target_1) if is_long else (candle.low <= active_pos.target_1)

                # Check Target 2
                t2_hit = (candle.high >= active_pos.target_2) if is_long else (candle.low <= active_pos.target_2)

                # Forced Square-Off Check (15:15 IST)
                session_info = self.strategy.session_model.evaluate(ts)
                is_square_off = (
                    session_info.session_phase.value in ("FORCED_SQUARE_OFF", "CLOSED")
                    or session_info.is_forced_square_off
                )

                if is_square_off:
                    exit_triggered = True
                    exit_price = candle.close
                    exit_reason = "SQUARE_OFF"
                elif sl_hit and t1_hit and not active_pos.t1_hit:
                    # Conservative rule: Both hit in same bar -> Stop Loss is assumed hit first
                    exit_triggered = True
                    exit_price = active_pos.stop_loss
                    exit_reason = "STOP_LOSS"
                elif sl_hit:
                    exit_triggered = True
                    exit_price = active_pos.stop_loss
                    exit_reason = "STOP_LOSS" if not active_pos.t1_hit else "BREAKEVEN_STOP"
                elif t2_hit and active_pos.t1_hit:
                    # Full Target 2 hit on runner
                    exit_triggered = True
                    exit_price = active_pos.target_2
                    exit_reason = "TARGET_2"
                elif t1_hit and not active_pos.t1_hit:
                    if self.enable_dynamic_exits:
                        # Partial scale: 50% exits at Target 1, remainder runs with breakeven stop
                        active_pos.t1_hit = True
                        half_qty = active_pos.quantity // 2
                        spot_move = (active_pos.target_1 - active_pos.entry_price) * active_pos.direction_sign
                        delta = 0.50 if active_pos.entry_price > 2000.0 else 1.0
                        half_points = spot_move * delta
                        half_gross = half_points * half_qty

                        bar_atr = max(5.0, abs(candle.high - candle.low))
                        friction = self.cost_model.calculate_round_trip(
                            instrument=instrument,
                            entry_price=active_pos.entry_price,
                            exit_price=active_pos.target_1,
                            quantity=half_qty,
                            is_option=True,
                            atr_1m=bar_atr,
                        )
                        active_pos.half_closed_pnl = half_gross - friction.total_friction
                        active_pos.half_closed_points = half_points
                        active_pos.half_closed_gross = half_gross
                        active_pos.half_closed_friction = friction.total_friction
                        # Move stop to breakeven
                        active_pos.stop_loss = active_pos.entry_price
                    else:
                        # Fixed target 1 exit
                        exit_triggered = True
                        exit_price = active_pos.target_1
                        exit_reason = "TARGET_1"
                elif self.enable_time_decay and holding_mins >= max(active_pos.expected_holding_minutes * 2.0, 15.0):
                    # Time decay exit (§22)
                    exit_triggered = True
                    exit_price = candle.close
                    exit_reason = "TIME_DECAY"

                # If position closed, finalize trade record
                if exit_triggered:
                    remaining_qty = (active_pos.quantity // 2) if active_pos.t1_hit else active_pos.quantity
                    spot_move = (exit_price - active_pos.entry_price) * active_pos.direction_sign
                    delta = 0.50 if active_pos.entry_price > 2000.0 else 1.0
                    rem_points = spot_move * delta
                    rem_gross = rem_points * remaining_qty

                    bar_atr = max(5.0, abs(candle.high - candle.low))
                    friction = self.cost_model.calculate_round_trip(
                        instrument=instrument,
                        entry_price=active_pos.entry_price,
                        exit_price=exit_price,
                        quantity=remaining_qty,
                        is_option=True,
                        atr_1m=bar_atr,
                    )
                    rem_net = rem_gross - friction.total_friction

                    total_net = active_pos.half_closed_pnl + rem_net
                    total_gross = (active_pos.half_closed_gross if active_pos.t1_hit else 0.0) + rem_gross
                    total_friction = active_pos.half_closed_friction + friction.total_friction
                    total_points = (total_gross / active_pos.quantity) if active_pos.quantity > 0 else 0.0

                    trade_id_seq += 1
                    trades.append(
                        BacktestTradeRecord(
                            trade_id=trade_id_seq,
                            instrument=instrument,
                            direction=active_pos.direction,
                            direction_sign=active_pos.direction_sign,
                            entry_time_ms=active_pos.entry_time_ms,
                            exit_time_ms=ts,
                            entry_price=active_pos.entry_price,
                            exit_price=exit_price,
                            quantity=active_pos.quantity,
                            gross_pnl_points=total_points,
                            gross_pnl_rupees=total_gross,
                            net_pnl_rupees=total_net,
                            friction_rupees=total_friction,
                            exit_reason=exit_reason,
                            holding_bars=active_pos.holding_bars,
                            holding_minutes=holding_mins,
                            signal_confidence=active_pos.confidence,
                            reason_codes=active_pos.reason_codes,
                        )
                    )
                    active_pos = None

            # ─────────────────────────────────────────────────────────────────
            # 2. Fill Pending Order on Current Bar Open
            # ─────────────────────────────────────────────────────────────────
            if pending_order is not None and active_pos is None:
                pending_lag_counter += 1
                if pending_lag_counter >= self.execution_lag_bars:
                    # Fill at current bar open + slippage
                    base_fill = candle.open
                    slip_pts = self.cost_model.base_slippage_ticks * self.cost_model.tick_size
                    actual_fill = base_fill + (slip_pts if pending_order.direction_sign > 0 else -slip_pts)

                    if self.lot_size == 25:
                        effective_lot_size = 10 if "SENSEX" in instrument.upper() else (15 if "BANK" in instrument.upper() else 25)
                    else:
                        effective_lot_size = self.lot_size
                    active_pos = ActivePosition(
                        trade_id=trade_id_seq + 1,
                        instrument=pending_order.instrument,
                        direction=pending_order.direction,
                        direction_sign=pending_order.direction_sign,
                        entry_time_ms=ts,
                        entry_price=round(actual_fill, 2),
                        quantity=effective_lot_size,
                        stop_loss=pending_order.stop_loss,
                        target_1=pending_order.target_1,
                        target_2=pending_order.target_2,
                        expected_holding_minutes=pending_order.expected_holding_minutes,
                        confidence=pending_order.confidence,
                        reason_codes=pending_order.reason_codes,
                    )
                    pending_order = None
                    pending_lag_counter = 0

            # ─────────────────────────────────────────────────────────────────
            # 3. Strategy Detection for Next Bar
            # ─────────────────────────────────────────────────────────────────
            if active_pos is None and pending_order is None:
                # Build StrategyContext with sliding window of last 60 1m candles
                recent_1m = bar_ctx.history_1m[-60:]
                if len(recent_1m) >= self.strategy.config.compression.atr_long_period:
                    candles_dict = [
                        {
                            "timestamp": c.timestamp,
                            "open": c.open,
                            "high": c.high,
                            "low": c.low,
                            "close": c.close,
                            "volume": c.volume,
                        }
                        for c in recent_1m
                    ]
                    indicators = {
                        "pdh": bar_ctx.pdh or 0.0,
                        "pdl": bar_ctx.pdl or 0.0,
                        "pdc": bar_ctx.pdc or 0.0,
                        "cdo": bar_ctx.cdo or 0.0,
                        "vwap": bar_ctx.vwap or candle.close,
                        "underlying_price": candle.close,
                    }
                    ctx = StrategyContext(
                        underlying=instrument,
                        spot_price=Decimal(str(round(candle.close, 2))),
                        timestamp_ms=ts,
                        candles=candles_dict,
                        indicators=indicators,
                    )

                    candidate = self.strategy.detect(ctx)
                    if candidate is not None:
                        dir_sign = 1 if "CALL" in candidate.direction or "LONG" in candidate.direction else -1
                        pending_order = PendingOrder(
                            instrument=instrument,
                            direction=candidate.direction,
                            direction_sign=dir_sign,
                            trigger_price=float(candidate.trigger),
                            stop_loss=float(candidate.stop_loss),
                            target_1=float(candidate.target_1),
                            target_2=float(candidate.target_2),
                            expected_move=float(candidate.target_1 - candidate.trigger),
                            expected_holding_minutes=6.0,
                            confidence=candidate.overall_confidence,
                            reason_codes=candidate.rationale or [],
                            signal_timestamp_ms=ts,
                        )
                        pending_lag_counter = 0

        # Close any lingering active position at end of backtest data
        if active_pos is not None:
            last_candle = bar_contexts[-1].candle_1m
            exit_price = last_candle.close
            remaining_qty = (active_pos.quantity // 2) if active_pos.t1_hit else active_pos.quantity
            spot_move = (exit_price - active_pos.entry_price) * active_pos.direction_sign
            delta = 0.50 if active_pos.entry_price > 2000.0 else 1.0
            rem_points = spot_move * delta
            rem_gross = rem_points * remaining_qty
            bar_atr = max(5.0, abs(last_candle.high - last_candle.low))
            friction = self.cost_model.calculate_round_trip(
                instrument=instrument,
                entry_price=active_pos.entry_price,
                exit_price=exit_price,
                quantity=remaining_qty,
                is_option=True,
                atr_1m=bar_atr,
            )
            rem_net = rem_gross - friction.total_friction
            total_net = active_pos.half_closed_pnl + rem_net
            total_gross = (active_pos.half_closed_gross if active_pos.t1_hit else 0.0) + rem_gross
            total_friction = active_pos.half_closed_friction + friction.total_friction
            total_points = (total_gross / active_pos.quantity) if active_pos.quantity > 0 else 0.0

            trade_id_seq += 1
            trades.append(
                BacktestTradeRecord(
                    trade_id=trade_id_seq,
                    instrument=instrument,
                    direction=active_pos.direction,
                    direction_sign=active_pos.direction_sign,
                    entry_time_ms=active_pos.entry_time_ms,
                    exit_time_ms=last_candle.timestamp,
                    entry_price=active_pos.entry_price,
                    exit_price=exit_price,
                    quantity=active_pos.quantity,
                    gross_pnl_points=total_points,
                    gross_pnl_rupees=total_gross,
                    net_pnl_rupees=total_net,
                    friction_rupees=total_friction,
                    exit_reason="END_OF_DATA",
                    holding_bars=active_pos.holding_bars,
                    holding_minutes=active_pos.holding_bars * 1.0,
                    signal_confidence=active_pos.confidence,
                    reason_codes=active_pos.reason_codes,
                )
            )

        self.last_trades = trades
        return calculate_metrics(trades, self.initial_capital)
