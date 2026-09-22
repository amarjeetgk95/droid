"""Synthetic Options Execution Simulator (Tier 3).

Models realistic Indian Index Options (SENSEX / NIFTY) contract execution:
- Strike selection: Nearest ATM strike (round 100 for SENSEX, round 50 for NIFTY)
- Premium pricing via Black-76 European model
- Theta time decay across bars held
- Delta sensitivity and non-linear gamma expansion
- Dynamic bid-ask spread expansion (1.0% to 3.0% half-spread penalty)
- Indian statutory options costs (STT 0.125% on sell premium, exchange charges, stamp duty, GST, ₹20 brokerage)
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, Literal, NamedTuple, Optional
import structlog

from app.quant.black76 import black76_price, black76_greeks
from app.quant.costs import (
    calculate_trade_costs,
    BSE_SENSEX_OPTIONS,
    StatutorySchedule,
    BSECostEngine,
)

logger = structlog.get_logger(__name__)


@dataclass
class OptionsTradeResult:
    entry_time: datetime
    exit_time: datetime
    strike: float
    option_type: Literal["CE", "PE"]
    underlying_entry: float
    underlying_exit: float
    premium_entry_raw: float
    premium_entry_exec: float    # After buy spread/slippage
    premium_exit_raw: float
    premium_exit_exec: float     # After sell spread/slippage
    options_gross_pnl: float     # Points per unit
    options_gross_roi_pct: float # Gross % return on invested premium
    total_statutory_cost: float  # In Rupees (₹)
    net_pnl_rupees: float        # In Rupees (₹)
    options_net_roi_pct: float   # Net % return after statutory friction
    bars_held: int
    delta_at_entry: float
    theta_per_day: float
    forward_entry: float = 0.0
    forward_exit: float = 0.0
    simulation_class: str = "SYNTHETIC / MODELED"
    pricing_model: str = "Black-76 (Forward-Underlying)"


class OptionsExecutionSimulator:
    """Simulates realistic options premium trajectories and transaction costs via Black-76 forward model."""

    def __init__(
        self,
        symbol: str = "SENSEX",
        lot_size: int = 10,
        strike_step: float = 100.0,
        default_iv: float = 0.14,           # 14% IV default for Indian indices
        risk_free_rate: float = 0.065,       # 6.5% RBI repo rate
        dividend_yield: float = 0.012,       # ~1.2% dividend yield on SENSEX/NIFTY
        spread_half_pct: float = 0.015,      # 1.5% half-spread slippage on premium
        cost_schedule: StatutorySchedule = BSE_SENSEX_OPTIONS,
    ):
        self.symbol = symbol
        self.lot_size = lot_size
        self.strike_step = strike_step
        self.default_iv = default_iv
        self.risk_free_rate = risk_free_rate
        self.dividend_yield = dividend_yield
        self.spread_half_pct = spread_half_pct
        self.cost_schedule = cost_schedule

    def select_atm_strike(self, spot_price: float) -> float:
        """Rounds spot price to the nearest tradeable ATM strike."""
        return round(spot_price / self.strike_step) * self.strike_step

    def simulate_trade(
        self,
        entry_time: datetime,
        exit_time: datetime,
        direction: int,                     # +1 = LONG (Buy CE), -1 = SHORT (Buy PE)
        spot_entry: float,
        spot_exit: float,
        bars_held: int,
        days_to_expiry: float = 4.0,        # Average weekly contract DTE
        custom_iv: Optional[float] = None,
        stress_multiplier: float = 1.0,
    ) -> OptionsTradeResult:
        """Simulates buying an ATM option contract at entry and closing at exit using Black-76 forward pricing."""
        sigma = custom_iv or self.default_iv
        option_type: Literal["CE", "PE"] = "CE" if direction == 1 else "PE"
        strike = self.select_atm_strike(spot_entry)

        # 1. Forward Price Calculation: F = S * exp((r - q) * T)
        t_entry = max(0.001, days_to_expiry / 365.0)
        carry_rate = self.risk_free_rate - self.dividend_yield
        forward_entry = spot_entry * math.exp(carry_rate * t_entry)

        p_entry_raw = black76_price(
            flag=option_type,
            f=forward_entry,
            k=strike,
            t=t_entry,
            r=self.risk_free_rate,
            sigma=sigma,
        )
        greeks_entry = black76_greeks(
            flag=option_type,
            f=forward_entry,
            k=strike,
            t=t_entry,
            r=self.risk_free_rate,
            sigma=sigma,
        )

        # Buy price with spread slippage: pay slightly higher
        p_entry_exec = p_entry_raw * (1.0 + self.spread_half_pct * stress_multiplier)

        # 2. Exit Option Pricing with Forward Decay
        time_decay_years = (bars_held * 15.0) / (375.0 * 252.0)  # Fraction of trading year
        t_exit = max(0.0001, t_entry - time_decay_years)
        forward_exit = spot_exit * math.exp(carry_rate * t_exit)

        p_exit_raw = black76_price(
            flag=option_type,
            f=forward_exit,
            k=strike,
            t=t_exit,
            r=self.risk_free_rate,
            sigma=sigma,
        )

        # Sell price with spread slippage: receive slightly lower
        p_exit_exec = max(0.05, p_exit_raw * (1.0 - self.spread_half_pct * stress_multiplier))

        # 3. Gross PnL
        options_gross_pts = p_exit_exec - p_entry_exec
        options_gross_roi = (options_gross_pts / max(0.1, p_entry_exec)) * 100.0

        # 4. Indian Statutory Costs
        # For options buyer: buy premium turnover = p_entry_exec * lot_size
        # sell premium turnover = p_exit_exec * lot_size
        buy_turnover = p_entry_exec * self.lot_size
        sell_turnover = p_exit_exec * self.lot_size

        costs = calculate_trade_costs(
            buy_turnover=buy_turnover,
            sell_turnover=sell_turnover,
            num_orders=2,
            schedule=self.cost_schedule,
            slippage_rate=0.0,  # Slippage already applied to premium above
            stress_multiplier=stress_multiplier,
        )

        total_cost_rupees = costs.total_cost
        gross_pnl_rupees = options_gross_pts * self.lot_size
        net_pnl_rupees = gross_pnl_rupees - total_cost_rupees
        net_roi = (net_pnl_rupees / max(1.0, buy_turnover)) * 100.0

        return OptionsTradeResult(
            entry_time=entry_time,
            exit_time=exit_time,
            strike=strike,
            option_type=option_type,
            underlying_entry=spot_entry,
            underlying_exit=spot_exit,
            premium_entry_raw=round(p_entry_raw, 2),
            premium_entry_exec=round(p_entry_exec, 2),
            premium_exit_raw=round(p_exit_raw, 2),
            premium_exit_exec=round(p_exit_exec, 2),
            options_gross_pnl=round(options_gross_pts, 2),
            options_gross_roi_pct=round(options_gross_roi, 2),
            total_statutory_cost=round(total_cost_rupees, 2),
            net_pnl_rupees=round(net_pnl_rupees, 2),
            options_net_roi_pct=round(net_roi, 2),
            bars_held=bars_held,
            delta_at_entry=round(greeks_entry.delta, 3),
            theta_per_day=round(greeks_entry.theta, 2),
            forward_entry=round(forward_entry, 2),
            forward_exit=round(forward_exit, 2),
            simulation_class="SYNTHETIC / MODELED",
            pricing_model="Black-76 (Forward-Underlying)",
        )

    def simulate_vertical_spread(
        self,
        spot_entry: float,
        spot_exit: float,
        direction: Literal["LONG", "SHORT"] | str | int = "LONG",
        holding_bars: int = 4,
        bar_minutes: int = 15,
        iv: Optional[float] = None,
        dte_entry: float = 4.0,
        strike_width: float = 300.0,
        lot_size: Optional[int] = None,
        contracts: int = 1,
        stress_multiplier: float = 1.0,
        spread_half_pct: float = 0.0,
    ) -> Dict[str, Any]:
        """Simulates defined-risk vertical spread using instance defaults."""
        return simulate_vertical_spread(
            spot_entry=spot_entry,
            spot_exit=spot_exit,
            direction=direction,
            holding_bars=holding_bars,
            bar_minutes=bar_minutes,
            iv=iv if iv is not None else self.default_iv,
            dte_entry=dte_entry,
            strike_width=strike_width,
            lot_size=lot_size if lot_size is not None else self.lot_size,
            contracts=contracts,
            stress_multiplier=stress_multiplier,
            risk_free_rate=self.risk_free_rate,
            dividend_yield=self.dividend_yield,
            spread_half_pct=spread_half_pct,
            strike_step=self.strike_step,
            cost_schedule=self.cost_schedule,
        )


def simulate_vertical_spread(
    spot_entry: float,
    spot_exit: float,
    direction: Literal["LONG", "SHORT"] | str | int = "LONG",
    holding_bars: int = 4,
    bar_minutes: int = 15,
    iv: float = 0.14,
    dte_entry: float = 4.0,
    strike_width: float = 300.0,
    lot_size: int = 10,
    contracts: int = 1,
    stress_multiplier: float = 1.0,
    risk_free_rate: float = 0.065,
    dividend_yield: float = 0.012,
    spread_half_pct: float = 0.0,
    strike_step: float = 100.0,
    cost_schedule: StatutorySchedule = BSE_SENSEX_OPTIONS,
) -> Dict[str, Any]:
    """Simulates defined-risk vertical debit spreads via Black-76 forward model.

    Direction logic:
    - "LONG" (Bull Call Spread):
      * Long Leg: ATM Call strike K1
      * Short Leg: OTM Call strike K2 = K1 + strike_width
    - "SHORT" (Bear Put Spread):
      * Long Leg: ATM Put strike K1
      * Short Leg: OTM Put strike K2 = K1 - strike_width

    Returns a comprehensive spread simulation dictionary with leg details,
    net Greeks, theta decay reduction vs naked option, and statutory costs.
    """
    dir_clean = str(direction).upper().strip()
    if dir_clean in ("1", "+1", "LONG", "BUY", "BULL"):
        spread_type = "Bull Call Spread"
        norm_direction = "LONG"
        option_type: Literal["CE", "PE"] = "CE"
        k1 = round(spot_entry / strike_step) * strike_step
        k2 = k1 + strike_width
    elif dir_clean in ("-1", "SHORT", "SELL", "BEAR"):
        spread_type = "Bear Put Spread"
        norm_direction = "SHORT"
        option_type = "PE"
        k1 = round(spot_entry / strike_step) * strike_step
        k2 = k1 - strike_width
    else:
        raise ValueError(f"Invalid spread direction '{direction}'. Must be 'LONG' (+1) or 'SHORT' (-1).")

    # 1. Forward Price Calculation: F = S * exp((r - q) * T)
    t_entry = max(0.0001, dte_entry / 365.0)
    carry_rate = risk_free_rate - dividend_yield
    forward_entry = spot_entry * math.exp(carry_rate * t_entry)

    time_decay_years = (holding_bars * bar_minutes) / (375.0 * 252.0)
    t_exit = max(0.00001, t_entry - time_decay_years)
    forward_exit = spot_exit * math.exp(carry_rate * t_exit)

    # 2. Black-76 Option Pricing for Both Legs
    # Entry pricing & Greeks
    p_long_entry_raw = black76_price(flag=option_type, f=forward_entry, k=k1, t=t_entry, r=risk_free_rate, sigma=iv)
    p_short_entry_raw = black76_price(flag=option_type, f=forward_entry, k=k2, t=t_entry, r=risk_free_rate, sigma=iv)
    greeks_long_entry = black76_greeks(flag=option_type, f=forward_entry, k=k1, t=t_entry, r=risk_free_rate, sigma=iv)
    greeks_short_entry = black76_greeks(flag=option_type, f=forward_entry, k=k2, t=t_entry, r=risk_free_rate, sigma=iv)

    if spread_half_pct > 0.0:
        p_long_entry = p_long_entry_raw * (1.0 + spread_half_pct * stress_multiplier)
        p_short_entry = max(0.05, p_short_entry_raw * (1.0 - spread_half_pct * stress_multiplier))
    else:
        p_long_entry = p_long_entry_raw
        p_short_entry = p_short_entry_raw

    # Exit pricing & Greeks
    p_long_exit_raw = black76_price(flag=option_type, f=forward_exit, k=k1, t=t_exit, r=risk_free_rate, sigma=iv)
    p_short_exit_raw = black76_price(flag=option_type, f=forward_exit, k=k2, t=t_exit, r=risk_free_rate, sigma=iv)
    greeks_long_exit = black76_greeks(flag=option_type, f=forward_exit, k=k1, t=t_exit, r=risk_free_rate, sigma=iv)
    greeks_short_exit = black76_greeks(flag=option_type, f=forward_exit, k=k2, t=t_exit, r=risk_free_rate, sigma=iv)

    if spread_half_pct > 0.0:
        p_long_exit = max(0.05, p_long_exit_raw * (1.0 - spread_half_pct * stress_multiplier))
        p_short_exit = p_short_exit_raw * (1.0 + spread_half_pct * stress_multiplier)
    else:
        p_long_exit = p_long_exit_raw
        p_short_exit = p_short_exit_raw

    # 3. Net Premium Calculation
    p_net_entry = p_long_entry - p_short_entry
    p_net_exit = p_long_exit - p_short_exit
    total_qty = lot_size * contracts

    # 4. Multi-Leg Statutory Cost Calculation (BSECostEngine)
    # Long Leg: Buy at entry (order 1), Sell at exit (order 2)
    buy_turnover_long = p_long_entry * total_qty
    sell_turnover_long = p_long_exit * total_qty
    costs_long = BSECostEngine.calculate_options_cost(
        buy_turnover=buy_turnover_long,
        sell_turnover=sell_turnover_long,
        num_orders=2,
        schedule=cost_schedule,
        stress_multiplier=stress_multiplier,
    )

    # Short Leg: Sell at entry (order 1), Buy at exit (order 2)
    sell_turnover_short = p_short_entry * total_qty
    buy_turnover_short = p_short_exit * total_qty
    costs_short = BSECostEngine.calculate_options_cost(
        buy_turnover=buy_turnover_short,
        sell_turnover=sell_turnover_short,
        num_orders=2,
        schedule=cost_schedule,
        stress_multiplier=stress_multiplier,
    )

    # Combined Statutory Costs: 2 orders entry + 2 orders exit = 4 orders
    total_buy_turnover = buy_turnover_long + buy_turnover_short
    total_sell_turnover = sell_turnover_long + sell_turnover_short
    costs_total = BSECostEngine.calculate_options_cost(
        buy_turnover=total_buy_turnover,
        sell_turnover=total_sell_turnover,
        num_orders=4,
        schedule=cost_schedule,
        stress_multiplier=stress_multiplier,
    )
    total_costs = costs_total.total_cost

    # 5. PnL & Payoff Bounds
    spread_gross_pts = p_net_exit - p_net_entry
    gross_pnl_rupees = spread_gross_pts * total_qty
    net_pnl_rupees = gross_pnl_rupees - total_costs
    net_roi_pct = (net_pnl_rupees / max(1.0, p_net_entry * total_qty)) * 100.0

    max_profit_pts = strike_width - p_net_entry
    max_profit_rupees = max_profit_pts * total_qty
    max_loss_pts = p_net_entry
    max_loss_rupees = max_loss_pts * total_qty

    # 6. Net Greeks
    net_delta = round(greeks_long_entry.delta - greeks_short_entry.delta, 4)
    net_theta = round(greeks_long_entry.theta - greeks_short_entry.theta, 4)
    net_gamma = round(greeks_long_entry.gamma - greeks_short_entry.gamma, 6)
    net_vega = round(greeks_long_entry.vega - greeks_short_entry.vega, 4)

    # 7. Theta Decay Reduction vs Naked Option
    naked_theta = greeks_long_entry.theta
    theta_decay_reduction_pct = (
        round((1.0 - abs(net_theta) / abs(naked_theta)) * 100.0, 2)
        if abs(naked_theta) > 1e-6 else 0.0
    )

    # Realized decay comparison over holding duration
    naked_loss_pts = max(0.0, p_long_entry - p_long_exit)
    spread_loss_pts = max(0.0, p_net_entry - p_net_exit)
    theta_loss_reduction_pct = (
        round((1.0 - spread_loss_pts / naked_loss_pts) * 100.0, 2)
        if naked_loss_pts > 1e-6 else 0.0
    )

    # Naked option benchmark
    naked_gross_pts = p_long_exit - p_long_entry
    naked_gross_pnl_rupees = naked_gross_pts * total_qty
    naked_net_pnl_rupees = naked_gross_pnl_rupees - costs_long.total_cost
    naked_roi_pct = (naked_net_pnl_rupees / max(1.0, buy_turnover_long)) * 100.0

    return {
        "spread_name": spread_type,
        "direction": norm_direction,
        "option_type": option_type,
        "spot_entry": spot_entry,
        "spot_exit": spot_exit,
        "forward_entry": round(forward_entry, 2),
        "forward_exit": round(forward_exit, 2),
        "holding_bars": holding_bars,
        "bar_minutes": bar_minutes,
        "dte_entry": dte_entry,
        "strike_width": strike_width,
        "lot_size": lot_size,
        "contracts": contracts,
        "total_quantity": total_qty,
        "legs": {
            "long_leg": {
                "strike": k1,
                "option_type": option_type,
                "action": "BUY",
                "premium_entry": round(p_long_entry, 2),
                "premium_exit": round(p_long_exit, 2),
                "delta": greeks_long_entry.delta,
                "theta": greeks_long_entry.theta,
                "gamma": greeks_long_entry.gamma,
                "vega": greeks_long_entry.vega,
            },
            "short_leg": {
                "strike": k2,
                "option_type": option_type,
                "action": "SELL",
                "premium_entry": round(p_short_entry, 2),
                "premium_exit": round(p_short_exit, 2),
                "delta": greeks_short_entry.delta,
                "theta": greeks_short_entry.theta,
                "gamma": greeks_short_entry.gamma,
                "vega": greeks_short_entry.vega,
            },
        },
        "net_premiums": {
            "p_net_entry": round(p_net_entry, 2),
            "p_net_exit": round(p_net_exit, 2),
            "net_debit": round(p_net_entry, 2),
        },
        "greeks": {
            "net_delta": net_delta,
            "net_theta": net_theta,
            "net_gamma": net_gamma,
            "net_vega": net_vega,
            "long_delta": greeks_long_entry.delta,
            "short_delta": greeks_short_entry.delta,
            "long_theta": greeks_long_entry.theta,
            "short_theta": greeks_short_entry.theta,
        },
        "theta_comparison": {
            "naked_theta_per_day": greeks_long_entry.theta,
            "spread_net_theta_per_day": net_theta,
            "theta_decay_reduction_pct": theta_decay_reduction_pct,
            "naked_loss_pts": round(naked_loss_pts, 2),
            "spread_loss_pts": round(spread_loss_pts, 2),
            "theta_loss_reduction_pct": theta_loss_reduction_pct,
        },
        "costs": {
            "stt": costs_total.stt,
            "exchange_charges": costs_total.exchange_charges,
            "sebi_charges": costs_total.sebi_charges,
            "stamp_duty": costs_total.stamp_duty,
            "brokerage": costs_total.brokerage,
            "gst": costs_total.gst,
            "slippage": costs_total.slippage,
            "total_cost": total_costs,
            "num_orders": 4,
            "long_leg_cost": costs_long.total_cost,
            "short_leg_cost": costs_short.total_cost,
        },
        "pnl": {
            "gross_pnl_pts": round(spread_gross_pts, 2),
            "gross_pnl_rupees": round(gross_pnl_rupees, 2),
            "total_statutory_cost": total_costs,
            "net_pnl_rupees": round(net_pnl_rupees, 2),
            "options_net_roi_pct": round(net_roi_pct, 2),
            "max_profit_pts": round(max_profit_pts, 2),
            "max_profit_rupees": round(max_profit_rupees, 2),
            "max_loss_pts": round(max_loss_pts, 2),
            "max_loss_rupees": round(max_loss_rupees, 2),
            "profit_capped": spread_gross_pts <= (max_profit_pts + 1e-4),
        },
        "naked_comparison": {
            "naked_entry": round(p_long_entry, 2),
            "naked_exit": round(p_long_exit, 2),
            "naked_gross_pnl_pts": round(naked_gross_pts, 2),
            "naked_gross_pnl_rupees": round(naked_gross_pnl_rupees, 2),
            "naked_total_cost": costs_long.total_cost,
            "naked_net_pnl_rupees": round(naked_net_pnl_rupees, 2),
            "naked_roi_pct": round(naked_roi_pct, 2),
            "naked_delta": greeks_long_entry.delta,
            "naked_theta": greeks_long_entry.theta,
        },
        # Flat convenience accessors:
        "net_entry": round(p_net_entry, 2),
        "net_exit": round(p_net_exit, 2),
        "gross_pnl_pts": round(spread_gross_pts, 2),
        "gross_pnl_rupees": round(gross_pnl_rupees, 2),
        "net_pnl_rupees": round(net_pnl_rupees, 2),
        "total_statutory_cost": total_costs,
        "net_delta": net_delta,
        "net_theta": net_theta,
        "net_gamma": net_gamma,
        "net_vega": net_vega,
        "theta_decay_reduction_pct": theta_decay_reduction_pct,
        "strike_long": k1,
        "strike_short": k2,
        "p_long_entry": round(p_long_entry, 2),
        "p_short_entry": round(p_short_entry, 2),
        "p_long_exit": round(p_long_exit, 2),
        "p_short_exit": round(p_short_exit, 2),
    }

