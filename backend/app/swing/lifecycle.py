"""
Swing Position Lifecycle & Trailing Stop Engine (v5.0 §18 & §19).
Manages multi-day positions:
  1. Trail to Break-Even at 1.5R.
  2. Trail along 20 EMA / 3-day low after 2.0R expansion.
  3. Evaluates target hits and stop hits.
"""
from __future__ import annotations

import time
from typing import Optional
from app.swing.models import SwingPosition, SwingSetup


def create_position_from_setup(
    setup: SwingSetup,
    fill_price: float,
    quantity: int,
) -> SwingPosition:
    """Instantiates an open SwingPosition from an entered setup."""
    return SwingPosition(
        setup_id=setup.setup_id,
        symbol=setup.symbol,
        sector=setup.sector,
        strategy=setup.strategy,
        entry_price=round(fill_price, 2),
        current_price=round(fill_price, 2),
        quantity=quantity,
        initial_stop=setup.stop_price,
        current_stop=setup.stop_price,
        trailing_method="STRUCTURAL_PIVOT",
        target_1=setup.target_1,
        target_2=setup.target_2,
        days_held=0,
        unrealized_pnl=0.0,
        pnl_pct=0.0,
        r_multiple=0.0,
        status="OPEN",
    )


def update_position_on_candle(
    position: SwingPosition,
    candle_close: float,
    candle_low: float,
    candle_high: float,
    current_ema20: Optional[float] = None,
    recent_3d_low: Optional[float] = None,
) -> SwingPosition:
    """
    Evaluates a daily bar against an open position:
      - Checks if Stop Hit (Low <= current_stop)
      - Checks if Target 2 Hit (High >= target_2)
      - Updates Trailing Stop according to R-multiples
      - Increments days held
    """
    pos = position.model_copy()
    pos.current_price = round(candle_close, 2)
    pos.days_held += 1

    risk_dist = pos.entry_price - pos.initial_stop
    if risk_dist <= 0:
        risk_dist = max(0.01, pos.entry_price * 0.02)

    gain_per_share = pos.current_price - pos.entry_price
    pos.unrealized_pnl = round(gain_per_share * pos.quantity, 2)
    pos.pnl_pct = round((gain_per_share / pos.entry_price) * 100.0, 2)
    pos.r_multiple = round(gain_per_share / risk_dist, 2)

    # Check Stop Loss Hit
    if candle_low <= pos.current_stop:
        pos.status = "CLOSED"
        pos.close_price = round(pos.current_stop, 2)
        pos.closed_at_utc = int(time.time() * 1000)
        pos.exit_reason = "STOP_LOSS_HIT"
        final_gain = pos.close_price - pos.entry_price
        pos.unrealized_pnl = round(final_gain * pos.quantity, 2)
        pos.pnl_pct = round((final_gain / pos.entry_price) * 100.0, 2)
        pos.r_multiple = round(final_gain / risk_dist, 2)
        return pos

    # Check Target 2 Hit
    if candle_high >= pos.target_2:
        pos.status = "CLOSED"
        pos.close_price = round(pos.target_2, 2)
        pos.closed_at_utc = int(time.time() * 1000)
        pos.exit_reason = "TARGET_2_HIT"
        final_gain = pos.close_price - pos.entry_price
        pos.unrealized_pnl = round(final_gain * pos.quantity, 2)
        pos.pnl_pct = round((final_gain / pos.entry_price) * 100.0, 2)
        pos.r_multiple = round(final_gain / risk_dist, 2)
        return pos

    # Trailing Stop Rules (§19):
    # 1. At 1.5R gain -> move stop to Break-Even (entry price)
    if pos.r_multiple >= 1.5 and pos.current_stop < pos.entry_price:
        pos.current_stop = round(pos.entry_price, 2)
        pos.trailing_method = "BREAK_EVEN"

    # 2. At 2.0R gain -> trail along 20 EMA or 3-day low (whichever is higher, but >= current_stop)
    if pos.r_multiple >= 2.0:
        candidate_stops = [pos.current_stop]
        if current_ema20 is not None and current_ema20 > pos.current_stop:
            candidate_stops.append(round(current_ema20, 2))
        if recent_3d_low is not None and recent_3d_low > pos.current_stop:
            candidate_stops.append(round(recent_3d_low, 2))

        new_stop = max(candidate_stops)
        if new_stop > pos.current_stop:
            pos.current_stop = new_stop
            pos.trailing_method = "EMA_20" if (current_ema20 and new_stop == current_ema20) else "THREE_DAY_LOW"

    return pos
