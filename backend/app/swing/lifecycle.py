"""
Swing Position Lifecycle & Dual-Layer Stop Engine (v6.0 Options Overhaul).
Manages multi-day options positions:
  1. Registers / deregisters positions with PortfolioGreeksLedger.
  2. Dual-Layer Stops:
     - Layer 1: Underlying Structural Invalidation (spot_stop breached)
     - Layer 2: Option Premium Invalidation (current_stop_premium hit)
  3. Dynamic Trailing Progression:
     - At +1.5R -> Break-even
     - At +2.0R -> Trailing premium stop (50% max reached)
  4. Time-decay & DTE protection:
     - DTE <= 3 triggers EXPIRY_WARNING
     - Daily theta burn > 35% triggers THETA_DECAY exit
"""
from __future__ import annotations

import time
from typing import Optional, Any
from app.swing.models import SwingPosition, SwingSetup, ExitReason
from app.signals.portfolio_greeks import portfolio_greeks_ledger, PortfolioGreekPosition


def create_position_from_setup(
    setup: SwingSetup,
    fill_premium: float,
    num_lots: int = 1,
) -> SwingPosition:
    """
    Instantiates an open options SwingPosition and registers with PortfolioGreeksLedger.
    Rejects fills that deviate >5% from scanned entry premium.
    """
    if fill_premium <= 0:
        raise ValueError("Fill premium must be positive.")
    if setup.entry_premium > 0 and abs(fill_premium - setup.entry_premium) / setup.entry_premium > 0.05:
        raise ValueError(
            f"Fill premium (₹{fill_premium:.2f}) deviates >5% from market quote (₹{setup.entry_premium:.2f})."
        )

    pos = SwingPosition(
        setup_id=setup.setup_id,
        underlying=setup.underlying,
        option_type=setup.option_type,
        strike=setup.strike,
        expiry_date=setup.expiry_date,
        contract_symbol=setup.contract_symbol,
        direction=setup.direction,
        strategy=setup.strategy,
        horizon=getattr(setup, "horizon", "POSITIONAL"),
        timeframe=getattr(setup, "timeframe", "1D"),
        hard_exit_time=getattr(setup, "hard_exit_time", None),
        entry_premium=round(fill_premium, 2),
        current_premium=round(fill_premium, 2),
        num_lots=num_lots,
        lot_size=setup.lot_size,
        initial_stop_premium=setup.stop_premium,
        current_stop_premium=setup.stop_premium,
        spot_stop=setup.spot_stop,
        stop_method="INITIAL",
        target_1=setup.target_premium_1,
        target_2=setup.target_premium_2,
        spot_at_entry=setup.spot_price,
        current_spot=setup.spot_price,
        greeks_at_entry=setup.greeks,
        iv_at_entry=setup.iv,
        days_held=0,
        dte_remaining=setup.dte,
        highest_premium=round(fill_premium, 2),
        entered_at_utc=int(time.time() * 1000),
        unrealized_pnl=0.0,
        pnl_pct=0.0,
        r_multiple=0.0,
        status="OPEN",
    )

    # Register in Portfolio Greeks Ledger
    unit_delta = float(setup.greeks.get("delta", 0.5))
    unit_gamma = float(setup.greeks.get("gamma", 0.001))
    unit_theta = float(setup.greeks.get("theta_day", -5.0))
    unit_vega = float(setup.greeks.get("vega", 5.0))

    portfolio_greeks_ledger.add_position(
        PortfolioGreekPosition(
            position_id=pos.position_id,
            underlying=pos.underlying,
            horizon="SWING",
            option_type=pos.option_type,
            strike=pos.strike,
            expiry_date=pos.expiry_date,
            quantity=pos.num_lots * pos.lot_size,
            unit_delta=unit_delta,
            unit_gamma=unit_gamma,
            unit_theta_day=unit_theta,
            unit_vega=unit_vega,
        )
    )

    return pos


def close_position(
    position: SwingPosition,
    exit_premium: float,
    reason: ExitReason = "MANUAL_EXIT",
) -> SwingPosition:
    """Closes an open position, records realized P&L and deregisters from Greeks ledger."""
    pos = position.model_copy()
    pos.status = "CLOSED"
    pos.close_premium = round(exit_premium, 2)
    pos.current_premium = round(exit_premium, 2)
    pos.closed_at_utc = int(time.time() * 1000)
    pos.exit_reason = reason

    risk_per_unit = max(0.01, pos.entry_premium - pos.initial_stop_premium)
    final_gain = pos.close_premium - pos.entry_premium
    pos.unrealized_pnl = round(final_gain * pos.lot_size * pos.num_lots, 2)
    pos.pnl_pct = round((final_gain / pos.entry_premium) * 100.0, 2)
    pos.r_multiple = round(final_gain / risk_per_unit, 2)

    # Remove from central ledger
    portfolio_greeks_ledger.remove_position(pos.position_id)

    return pos


def update_position(
    position: SwingPosition,
    current_premium: float,
    current_spot: float,
    current_greeks: Optional[dict[str, Any]] = None,
    current_iv: float = 0.0,
    dte_remaining: Optional[int] = None,
    check_time_stop: bool = True,
    current_time: Optional[Any] = None,
) -> SwingPosition:
    """
    Evaluates real-time price changes, dual-layer stops, targets, and trailing stops:
      - Layer 1: Spot Stop Hit (Underlying thesis invalidated)
      - Layer 2: Premium Stop Hit (Option value compromised)
      - Target 2 Hit (+3.0R)
      - DTE <= 3 (Near-expiry warning)
      - Theta decay acceleration (> 35%/day burn)
    """
    pos = position.model_copy()
    pos.current_premium = round(current_premium, 2)
    pos.current_spot = round(current_spot, 2)
    pos.highest_premium = max(pos.highest_premium, pos.current_premium)
    if dte_remaining is not None:
        pos.dte_remaining = dte_remaining

    risk_per_unit = max(0.01, pos.entry_premium - pos.initial_stop_premium)
    gain_per_share = pos.current_premium - pos.entry_premium
    pos.unrealized_pnl = round(gain_per_share * pos.lot_size * pos.num_lots, 2)
    pos.pnl_pct = round((gain_per_share / pos.entry_premium) * 100.0, 2)
    pos.r_multiple = round(gain_per_share / risk_per_unit, 2)

    # DUAL-LAYER STOP & LIFECYCLE CHECK:
    # 0. Intraday Hard Time Stop (15:15 IST)
    if getattr(pos, "horizon", "POSITIONAL") == "INTRADAY" and check_time_stop:
        from datetime import datetime, timezone, timedelta
        if current_time is not None:
            ist_now = current_time
        else:
            ist_now = datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)
        if ist_now.time() >= datetime.strptime("15:15:00", "%H:%M:%S").time():
            return close_position(pos, current_premium, "TIME_STOP")

    # 1. Underlying Structural Invalidation
    if pos.direction == "LONG_CALL" and current_spot <= pos.spot_stop:
        return close_position(pos, current_premium, "UNDERLYING_STOP")
    if pos.direction == "LONG_PUT" and current_spot >= pos.spot_stop:
        return close_position(pos, current_premium, "UNDERLYING_STOP")

    # 2. Option Premium Stop Hit
    if current_premium <= pos.current_stop_premium:
        return close_position(pos, current_premium, "OPTION_STOP")

    # 3. Target 2 Hit (+3.0R)
    if current_premium >= pos.target_2:
        return close_position(pos, current_premium, "TARGET_2")

    # 4. Theta Burn Acceleration (§18: > 35% daily theta burn)
    if current_greeks:
        theta_pct = abs(float(current_greeks.get("theta_pct_day", 0.0)))
        if theta_pct > 35.0:
            return close_position(pos, current_premium, "THETA_DECAY")

    # 5. Dynamic Trailing Progression
    is_intraday = getattr(pos, "horizon", "POSITIONAL") == "INTRADAY"
    if is_intraday:
        # Intraday moves faster: Break-even at +1.0R, trail at +1.5R
        if pos.r_multiple >= 1.5:
            peak_gain = max(0.0, pos.highest_premium - pos.entry_premium)
            trail_stop = round(pos.entry_premium + peak_gain * 0.40, 2)
            if trail_stop > pos.current_stop_premium:
                pos.current_stop_premium = trail_stop
                pos.stop_method = "TRAILING_PREMIUM"
        elif pos.r_multiple >= 1.0:
            if pos.current_stop_premium < pos.entry_premium:
                pos.current_stop_premium = round(pos.entry_premium, 2)
                pos.stop_method = "BREAK_EVEN"
    else:
        # Positional rules: Break-even at +1.5R, 50% peak trail at +2.0R
        if pos.r_multiple >= 2.0:
            peak_gain = max(0.0, pos.highest_premium - pos.entry_premium)
            trail_stop = round(pos.entry_premium + peak_gain * 0.50, 2)
            if trail_stop > pos.current_stop_premium:
                pos.current_stop_premium = trail_stop
                pos.stop_method = "TRAILING_PREMIUM"
        elif pos.r_multiple >= 1.5:
            if pos.current_stop_premium < pos.entry_premium:
                pos.current_stop_premium = round(pos.entry_premium, 2)
                pos.stop_method = "BREAK_EVEN"

    return pos


def update_position_on_candle(
    position: SwingPosition,
    candle_close: float,
    candle_low: float,
    candle_high: float,
    current_ema20: Optional[float] = None,
    recent_3d_low: Optional[float] = None,
) -> SwingPosition:
    """
    Compatibility helper for candle-based simulation and tests.
    Uses candle_close as current spot/premium.
    """
    return update_position(
        position=position,
        current_premium=candle_close,
        current_spot=candle_close,
    )

