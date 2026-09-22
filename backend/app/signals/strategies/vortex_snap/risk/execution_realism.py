"""
Execution Realism & Transaction Cost Engine (§29).

Models real-world institutional friction for Indian index derivatives:
- Brokerage (Rs 20 flat per executed order)
- Exchange turnover fees (NSE: 0.053% on premium)
- STT (0.10% on sell-side turnover)
- GST (18% on brokerage + exchange charges)
- Stamp duty (0.003% on buy side)
- Instrument-specific slippage and latency delays
"""
from __future__ import annotations

from typing import Literal, Tuple
from pydantic import BaseModel, Field


class TradeFriction(BaseModel):
    """Breakdown of all friction costs for a trade."""
    brokerage: float = 40.0         # 20 entry + 20 exit
    exchange_charges: float = 0.0
    stt: float = 0.0
    gst: float = 0.0
    stamp_duty: float = 0.0
    total_statutory_fees: float = 0.0
    slippage_points: float = 0.0
    slippage_cost: float = 0.0
    total_friction_cost: float = 0.0


class ExecutionRealismModel:
    """Calculates realistic simulated fills and net P&L after costs."""

    def __init__(
        self,
        base_slippage_points: float = 1.5,
        execution_delay_ms: int = 150,
    ) -> None:
        self.base_slippage_points = base_slippage_points
        self.execution_delay_ms = execution_delay_ms

    def simulate_fill(
        self,
        theoretical_price: float,
        direction: int,  # +1 (LONG), -1 (SHORT)
        volatility_multiplier: float = 1.0,
    ) -> Tuple[float, float]:
        """Simulate realistic execution fill with slippage.

        Returns:
            (simulated_price, slippage_points)
        """
        slip = self.base_slippage_points * max(volatility_multiplier, 0.8)
        if direction > 0:
            # Buying pays higher price
            fill = theoretical_price + slip
        else:
            # Selling receives lower price
            fill = theoretical_price - slip

        return round(fill, 2), round(slip, 2)

    def calculate_trade_costs(
        self,
        instrument: Literal["NIFTY", "BANKNIFTY", "SENSEX"],
        entry_price: float,
        exit_price: float,
        lots: int = 1,
        lot_size: int = 25,
    ) -> TradeFriction:
        """Calculate complete statutory fees, GST, STT, and slippage.

        Args:
            instrument: Target index.
            entry_price: Executed entry price.
            exit_price: Executed exit price.
            lots: Number of traded lots.
            lot_size: Contract multiplier (e.g. 25 for NIFTY, 15 for BANKNIFTY).

        Returns:
            TradeFriction breakdown.
        """
        qty = lots * lot_size
        buy_turnover = entry_price * qty
        sell_turnover = exit_price * qty
        total_turnover = buy_turnover + sell_turnover

        # 1. Brokerage (Rs 20 flat per executed leg)
        brokerage = 40.0

        # 2. Exchange turnover charge (NSE: ~0.053% on premium/turnover)
        exch_rate = 0.00053
        exchange_charges = total_turnover * exch_rate

        # 3. STT (Securities Transaction Tax) - 0.1% on sell side
        stt_rate = 0.0010
        stt = sell_turnover * stt_rate

        # 4. GST (18% on brokerage + exchange charges)
        gst = (brokerage + exchange_charges) * 0.18

        # 5. Stamp duty (0.003% on buy side)
        stamp_duty = buy_turnover * 0.00003

        statutory_fees = brokerage + exchange_charges + stt + gst + stamp_duty

        # Slippage calculation
        slip_pts = self.base_slippage_points * 2  # entry + exit slippage
        slip_cost = slip_pts * qty

        total_friction = statutory_fees + slip_cost

        return TradeFriction(
            brokerage=round(brokerage, 2),
            exchange_charges=round(exchange_charges, 2),
            stt=round(stt, 2),
            gst=round(gst, 2),
            stamp_duty=round(stamp_duty, 2),
            total_statutory_fees=round(statutory_fees, 2),
            slippage_points=round(slip_pts, 2),
            slippage_cost=round(slip_cost, 2),
            total_friction_cost=round(total_friction, 2),
        )
