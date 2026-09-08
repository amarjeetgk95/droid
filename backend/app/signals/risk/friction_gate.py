"""
Net Edge & Friction Gate (§27, §28).
Ensures no trade is executed unless Expected Net Edge > 0 after accounting for:
  1. Brokerage (₹20/order)
  2. Exchange Turnover, SEBI charges, Stamp Duty, GST, and STT (Sell-side 0.125%)
  3. Dynamic Bid-Ask Spread penalty
  4. Adverse Execution Slippage
  5. Options Theta / Charm decay drag during the expected holding duration

Rejection Code: REJECT_FRICTION / REJECT_NET_EDGE
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
from pydantic import BaseModel, Field

from app.signals.strategies.base import SignalCandidate
from app.quant.costs import calculate_option_costs


class NetEdgeResult(BaseModel):
    passed: bool
    expected_gross_edge_pts: float
    total_friction_pts: float
    expected_net_edge_pts: float
    cost_to_target_ratio_pct: float
    net_reward_risk_ratio: float
    rejection_reason: Optional[str] = None
    breakdown: dict[str, float] = Field(default_factory=dict)


class FrictionGate:
    """
    Evaluates net profitability after statutory charges, slippage, and spread.
    """

    def __init__(
        self,
        min_net_reward_risk: float = 1.10,
        max_cost_to_target_ratio: float = 0.45,  # Max 45% of gross target eaten by costs
        default_nifty_lot: int = 75,
        default_banknifty_lot: int = 30,
        default_sensex_lot: int = 20,
    ):
        self.min_net_reward_risk = min_net_reward_risk
        self.max_cost_to_target_ratio = max_cost_to_target_ratio
        self.lot_sizes = {
            "NIFTY": default_nifty_lot,
            "BANKNIFTY": default_banknifty_lot,
            "SENSEX": default_sensex_lot,
        }

    def evaluate(
        self,
        candidate: SignalCandidate,
        estimated_premium: Optional[float] = None,
        spread_pts: Optional[float] = None,
        slippage_pct: float = 0.002,
        expected_holding_seconds: Optional[int] = None,
    ) -> NetEdgeResult:
        u = candidate.underlying
        lot_size = self.lot_sizes.get(u, 75)
        
        # Spot risk and target points
        spot_risk = float(candidate.risk_points)
        spot_target = float(candidate.target_1 - candidate.trigger) if candidate.direction == "LONG_CALL" else float(candidate.trigger - candidate.target_1)
        spot_target = max(0.1, spot_target)

        # Delta estimate (approx 0.50 for ATM options if not provided)
        delta = 0.50
        if candidate.greeks and "delta" in candidate.greeks:
            delta = abs(float(candidate.greeks["delta"]))

        # Premium estimate (approx 1.0% of spot if not provided)
        premium = estimated_premium
        if premium is None or premium <= 0:
            premium = float(candidate.spot_price) * 0.008

        # Projected Option Points Move
        gross_option_target_pts = spot_target * delta
        gross_option_risk_pts = spot_risk * delta

        # Dynamic Spread Penalty (Option points)
        if spread_pts is not None and spread_pts > 0:
            opt_spread = spread_pts
        else:
            opt_spread = 1.0 if u == "NIFTY" else (3.0 if u == "BANKNIFTY" else 5.0)

        # Option Turnover calculation for statutory costs
        buy_turnover = premium * lot_size
        sell_turnover = (premium + gross_option_target_pts) * lot_size
        cost_breakdown = calculate_option_costs(
            buy_turnover=buy_turnover,
            sell_turnover=sell_turnover,
            num_orders=2,
            brokerage_per_order=20.0,
            slippage_pct=slippage_pct,
        )

        # Convert statutory rupee cost to option points
        statutory_points = cost_breakdown.total_cost / lot_size

        # Theta Decay Drag (Holding time)
        holding_sec = expected_holding_seconds or candidate.time_stop_seconds or candidate.ttl_seconds
        theta_drag_pts = 0.0
        if candidate.greeks and "theta" in candidate.greeks:
            theta_day = abs(float(candidate.greeks["theta"]))
            theta_hour = theta_day / 6.25  # ~6.25 trading hours per NSE session
            theta_drag_pts = theta_hour * (holding_sec / 3600.0)
        else:
            # Default minor decay estimate: ~0.08 pts/hr for Nifty
            theta_drag_pts = (0.15 if candidate.is_scalp else 0.45)

        # Total Friction (in option premium points)
        total_friction_pts = opt_spread + statutory_points + theta_drag_pts

        # Expected Net Edge (Option points)
        net_edge_pts = gross_option_target_pts - total_friction_pts

        # Ratios
        cost_ratio = (total_friction_pts / gross_option_target_pts) if gross_option_target_pts > 0 else 1.0
        net_reward_risk = (net_edge_pts / (gross_option_risk_pts + total_friction_pts)) if (gross_option_risk_pts + total_friction_pts) > 0 else 0.0

        rejection: Optional[str] = None
        if net_edge_pts <= 0:
            rejection = f"REJECT_NET_EDGE: Total friction ({total_friction_pts:.2f} pts) exceeds gross expected move ({gross_option_target_pts:.2f} pts)"
        elif cost_ratio > self.max_cost_to_target_ratio:
            rejection = f"REJECT_FRICTION: Friction consumes {cost_ratio * 100.0:.1f}% of target (max allowed: {self.max_cost_to_target_ratio * 100.0:.1f}%)"
        elif net_reward_risk < self.min_net_reward_risk:
            rejection = f"REJECT_POOR_NET_RR: Net R/R ({net_reward_risk:.2f}) is below minimum threshold ({self.min_net_reward_risk:.2f})"

        passed = (rejection is None)

        return NetEdgeResult(
            passed=passed,
            expected_gross_edge_pts=round(gross_option_target_pts, 2),
            total_friction_pts=round(total_friction_pts, 2),
            expected_net_edge_pts=round(net_edge_pts, 2),
            cost_to_target_ratio_pct=round(cost_ratio * 100.0, 1),
            net_reward_risk_ratio=round(net_reward_risk, 2),
            rejection_reason=rejection,
            breakdown={
                "spread_pts": round(opt_spread, 2),
                "statutory_charges_rupees": round(cost_breakdown.total_cost, 2),
                "statutory_pts": round(statutory_points, 2),
                "theta_decay_drag_pts": round(theta_drag_pts, 2),
                "slippage_pts": round(cost_breakdown.slippage / lot_size, 2),
            },
        )


friction_gate = FrictionGate()
