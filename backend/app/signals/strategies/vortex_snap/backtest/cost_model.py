"""
Indian Derivative Transaction Cost & Slippage Model (§29, §30).

Implements statutory friction and execution reality:
- Brokerage: ₹20 / order
- Securities Transaction Tax (STT): 0.1% on options sell, 0.0125% on futures sell
- Exchange turnover charge: NSE 0.0505%, BSE 0.0375%
- SEBI turnover fee: ₹10 / crore (0.0001%)
- Stamp duty: 0.003% on buy turnover
- GST: 18% on (Brokerage + Exchange turnover charges + SEBI charges)
- Execution slippage: Base tick slippage + volatility scaling + stress multiplier
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any


@dataclass
class RoundTripFriction:
    """Detailed breakdown of round-trip transaction costs."""
    brokerage: float
    stt: float
    exchange_charges: float
    sebi_charges: float
    stamp_duty: float
    gst: float
    total_statutory_taxes: float
    entry_slippage_points: float
    exit_slippage_points: float
    total_slippage_cost: float
    total_friction: float

    def to_dict(self) -> Dict[str, float]:
        return {
            "brokerage": round(self.brokerage, 2),
            "stt": round(self.stt, 2),
            "exchange_charges": round(self.exchange_charges, 2),
            "sebi_charges": round(self.sebi_charges, 2),
            "stamp_duty": round(self.stamp_duty, 2),
            "gst": round(self.gst, 2),
            "total_statutory_taxes": round(self.total_statutory_taxes, 2),
            "entry_slippage_points": round(self.entry_slippage_points, 2),
            "exit_slippage_points": round(self.exit_slippage_points, 2),
            "total_slippage_cost": round(self.total_slippage_cost, 2),
            "total_friction": round(self.total_friction, 2),
        }


class TransactionCostModel:
    """Computes realistic round-trip costs and slippage for index trades."""

    def __init__(
        self,
        brokerage_per_order: float = 20.0,
        cost_stress_multiplier: float = 1.0,
        slippage_stress_multiplier: float = 1.0,
        base_slippage_ticks: int = 1,
        tick_size: float = 0.05,
    ):
        self.brokerage_per_order = brokerage_per_order
        self.cost_stress_multiplier = cost_stress_multiplier
        self.slippage_stress_multiplier = slippage_stress_multiplier
        self.base_slippage_ticks = base_slippage_ticks
        self.tick_size = tick_size

    def calculate_round_trip(
        self,
        instrument: str,
        entry_price: float,
        exit_price: float,
        quantity: int,
        is_option: bool = True,
        atr_1m: float = 10.0,
        option_premium_entry: Optional[float] = None,
        option_premium_exit: Optional[float] = None,
    ) -> RoundTripFriction:
        """Calculates exact friction for a completed round-trip trade."""
        if is_option:
            if option_premium_entry is not None and option_premium_exit is not None:
                p_buy = max(0.50, option_premium_entry)
                p_sell = max(0.50, option_premium_exit)
            elif entry_price > 2000.0:
                # Underlying spot price was passed (e.g. SENSEX ~87000, NIFTY ~24000).
                # Convert to realistic Indian ATM weekly option premium (~0.5% of spot)
                p_buy = max(20.0, entry_price * 0.005)
                # Option points gained/lost via ATM delta (~0.50)
                opt_points = (exit_price - entry_price) * 0.50
                p_sell = max(0.50, p_buy + opt_points)
            else:
                # Direct option premium was passed (e.g. 120.0 to 150.0 in unit tests)
                p_buy = max(0.50, entry_price)
                p_sell = max(0.50, exit_price)

            turnover_buy = p_buy * quantity
            turnover_sell = p_sell * quantity

            # 0.1% on sell premium (Indian Finance Act STT)
            stt = (turnover_sell * 0.001) * self.cost_stress_multiplier
            # Exchange charge 0.05% on option turnover
            exch_rate = 0.0005
            # Slippage on option premium (scaled by option ATR ~ 0.50 * spot_atr)
            opt_atr = (atr_1m * 0.50) if entry_price > 2000.0 else atr_1m
            base_slip = (self.base_slippage_ticks * self.tick_size) + (opt_atr * 0.04)
        else:
            turnover_buy = entry_price * quantity
            turnover_sell = exit_price * quantity
            # Futures 0.0125% on sell
            stt = (turnover_sell * 0.000125) * self.cost_stress_multiplier
            exch_rate = 0.0002
            base_slip = (self.base_slippage_ticks * self.tick_size) + (atr_1m * 0.04)

        # Brokerage (₹20 buy + ₹20 sell)
        brokerage = (self.brokerage_per_order * 2.0) * self.cost_stress_multiplier

        exch_charges = ((turnover_buy + turnover_sell) * exch_rate) * self.cost_stress_multiplier
        sebi_charges = ((turnover_buy + turnover_sell) * 0.000001) * self.cost_stress_multiplier
        stamp_duty = (turnover_buy * 0.00003) * self.cost_stress_multiplier  # 0.003% on buy
        gst = ((brokerage + exch_charges + sebi_charges) * 0.18) * self.cost_stress_multiplier

        total_taxes = brokerage + stt + exch_charges + sebi_charges + stamp_duty + gst

        # Slippage calculation
        entry_slip = base_slip * self.slippage_stress_multiplier
        exit_slip = base_slip * self.slippage_stress_multiplier
        total_slip_cost = (entry_slip + exit_slip) * quantity

        total_friction = total_taxes + total_slip_cost

        return RoundTripFriction(
            brokerage=brokerage,
            stt=stt,
            exchange_charges=exch_charges,
            sebi_charges=sebi_charges,
            stamp_duty=stamp_duty,
            gst=gst,
            total_statutory_taxes=total_taxes,
            entry_slippage_points=entry_slip,
            exit_slippage_points=exit_slip,
            total_slippage_cost=total_slip_cost,
            total_friction=total_friction,
        )
