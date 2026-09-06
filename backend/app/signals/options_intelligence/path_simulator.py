"""
Options Intelligence: Path-Dependent Option Simulation & Realistic Transaction Costs
Implements §30 and §31 of Institutional Options Engine.

Models:
  - First and second order Greek trajectory:
      dOption = (Delta * dSpot) + (0.5 * Gamma * dSpot^2) + (Theta * dt) + (Vega * dIV)
  - Realistic Indian F&O regulatory costs & friction:
      * Brokerage (₹20/order)
      * STT (0.1% on option sell premium)
      * Exchange Turnover (0.0505% on premium turnover)
      * GST (18% on brokerage + turnover charges)
      * SEBI charges (₹10 / crore)
      * Stamp duty (0.003% on buy side)
      * Bid-Ask half-spread drag on entry & exit
      * Execution slippage
  - Multi-scenario path simulations:
      1. Fast Favorable Move (Quick thrust to target)
      2. Slow Favorable Move (Reaches target with maximum theta drag)
      3. Sideways Market (Zero underlying change, pure theta bleed)
      4. Adverse Move (Hits underlying stop loss)
      5. IV Crush Scenario (Underlying hits target, but IV drops by e.g. 15-25%)
"""
from __future__ import annotations

import math
from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.signals.options_intelligence.greeks import BlackScholesGreeks, GreeksResult


class IndianOptionCosts(BaseModel):
    brokerage_per_order: float = 20.0  # ₹20 flat per executed order
    stt_rate_sell: float = 0.001  # 0.1% on option premium at sell
    exchange_turnover_rate: float = 0.000505  # 0.0505% on premium turnover
    gst_rate: float = 0.18  # 18% on (brokerage + exchange charges)
    sebi_charge_rate: float = 0.000001  # ₹10 per crore
    stamp_duty_rate_buy: float = 0.00003  # 0.003% on buy turnover
    default_spread_pts: float = 1.0  # ₹1.00 average bid-ask spread
    default_slippage_pts: float = 0.5  # ₹0.50 average execution slippage

    def calculate_total_costs(
        self,
        entry_premium: float,
        exit_premium: float,
        quantity: int,
        spread_pts: Optional[float] = None,
        slippage_pts: Optional[float] = None,
    ) -> dict[str, float]:
        """
        Calculates complete institutional friction breakdown for round-trip option trade.
        """
        if quantity <= 0 or entry_premium <= 0:
            return {"total_friction": 0.0}

        spread = self.default_spread_pts if spread_pts is None else spread_pts
        slippage = self.default_slippage_pts if slippage_pts is None else slippage_pts

        buy_turnover = entry_premium * quantity
        sell_turnover = max(0.0, exit_premium) * quantity
        total_turnover = buy_turnover + sell_turnover

        # 1. Statutory taxes & broker commissions
        brokerage = self.brokerage_per_order * 2.0  # Entry + Exit
        stt = sell_turnover * self.stt_rate_sell  # STT applies on sell in Indian F&O
        exchange_charges = total_turnover * self.exchange_turnover_rate
        gst = (brokerage + exchange_charges) * self.gst_rate
        sebi = total_turnover * self.sebi_charge_rate
        stamp_duty = buy_turnover * self.stamp_duty_rate_buy
        statutory_taxes = round(brokerage + stt + exchange_charges + gst + sebi + stamp_duty, 2)

        # 2. Market microstructure friction (half spread + slippage on entry and exit)
        # Entry buys at ask (half spread above mid + slippage)
        # Exit sells at bid (half spread below mid - slippage)
        market_friction_per_unit = spread + (slippage * 2.0)
        market_friction_rupees = round(market_friction_per_unit * quantity, 2)

        total_friction = round(statutory_taxes + market_friction_rupees, 2)

        return {
            "brokerage": brokerage,
            "stt": round(stt, 2),
            "exchange_charges": round(exchange_charges, 2),
            "gst": round(gst, 2),
            "sebi": round(sebi, 2),
            "stamp_duty": round(stamp_duty, 2),
            "statutory_taxes": statutory_taxes,
            "market_friction_rupees": market_friction_rupees,
            "total_friction": total_friction,
            "friction_per_share": round(total_friction / quantity, 2) if quantity > 0 else 0.0,
        }


class ScenarioOutcome(BaseModel):
    scenario_name: str
    underlying_exit_price: float
    spot_change: float
    option_entry_price: float
    option_exit_price: float
    gross_pnl_per_share: float
    gross_pnl_total: float
    friction_total: float
    net_pnl_total: float
    net_return_pct: float
    holding_hours: float
    theta_drag_total: float
    vega_pnl_total: float
    is_profitable: bool


class PathSimulationReport(BaseModel):
    underlying: str
    strike: float
    option_type: Literal["CE", "PE"]
    entry_spot: float
    entry_premium: float
    quantity: int
    initial_delta: float
    initial_gamma: float
    initial_theta_hour: float
    initial_vega: float
    iv: float
    dte_days: float

    # Scenarios
    fast_target: ScenarioOutcome
    slow_target: ScenarioOutcome
    sideways: ScenarioOutcome
    adverse_stop: ScenarioOutcome
    iv_crush_target: ScenarioOutcome

    # Decision metrics
    is_economically_viable: bool
    viability_rationale: list[str]


class PathDependentOptionSimulator:
    """
    Simulates path-dependent price evolution for an option candidate.
    Verifies that expected target moves actually generate positive net expectancy
    after theta decay, potential IV crush, bid-ask spread, and exchange friction.
    """

    def __init__(self, cost_model: Optional[IndianOptionCosts] = None):
        self.costs = cost_model or IndianOptionCosts()

    def simulate_path_scenario(
        self,
        scenario_name: str,
        spot_start: float,
        spot_end: float,
        strike: float,
        time_to_expiry_start_years: float,
        holding_hours: float,
        iv_start: float,
        iv_end: float,
        option_type: Literal["CE", "PE"],
        quantity: int,
        entry_premium: Optional[float] = None,
    ) -> ScenarioOutcome:
        """
        Simulates an explicit path scenario from start to end.
        Re-prices the option using Black-Scholes at t_end with iv_end and spot_end.
        """
        # Starting theoretical premium if not provided
        if entry_premium is None or entry_premium <= 0:
            entry_premium = BlackScholesGreeks.calculate_price(
                spot=spot_start,
                strike=strike,
                time_to_expiry_years=time_to_expiry_start_years,
                volatility=iv_start,
                option_type=option_type,
            )

        # Elapsed time in years (based on 252 trading days * 6.25 hours = 1575 hours/year)
        elapsed_years = holding_hours / 1575.0
        time_to_expiry_end = max(1e-6, time_to_expiry_start_years - elapsed_years)

        # Theoretical exit premium
        exit_premium = BlackScholesGreeks.calculate_price(
            spot=spot_end,
            strike=strike,
            time_to_expiry_years=time_to_expiry_end,
            volatility=iv_end,
            option_type=option_type,
        )

        gross_diff = exit_premium - entry_premium
        gross_total = round(gross_diff * quantity, 2)

        # Detailed friction calculation
        friction_dict = self.costs.calculate_total_costs(
            entry_premium=entry_premium,
            exit_premium=exit_premium,
            quantity=quantity,
        )
        friction_total = friction_dict["total_friction"]
        net_pnl = round(gross_total - friction_total, 2)
        invested_capital = entry_premium * quantity
        net_return_pct = round((net_pnl / invested_capital * 100.0), 2) if invested_capital > 0 else 0.0

        # Estimate components (Theta drag vs Delta/Vega)
        # Theta drag = premium difference if spot and IV stayed unchanged
        base_decay_price = BlackScholesGreeks.calculate_price(
            spot=spot_start,
            strike=strike,
            time_to_expiry_years=time_to_expiry_end,
            volatility=iv_start,
            option_type=option_type,
        )
        theta_drag_total = round((entry_premium - base_decay_price) * quantity, 2)

        # Vega component = difference due strictly to IV change
        vega_test_price = BlackScholesGreeks.calculate_price(
            spot=spot_start,
            strike=strike,
            time_to_expiry_years=time_to_expiry_start_years,
            volatility=iv_end,
            option_type=option_type,
        )
        vega_pnl_total = round((vega_test_price - entry_premium) * quantity, 2)

        return ScenarioOutcome(
            scenario_name=scenario_name,
            underlying_exit_price=spot_end,
            spot_change=round(spot_end - spot_start, 2),
            option_entry_price=round(entry_premium, 2),
            option_exit_price=round(exit_premium, 2),
            gross_pnl_per_share=round(gross_diff, 2),
            gross_pnl_total=gross_total,
            friction_total=friction_total,
            net_pnl_total=net_pnl,
            net_return_pct=net_return_pct,
            holding_hours=round(holding_hours, 2),
            theta_drag_total=theta_drag_total,
            vega_pnl_total=vega_pnl_total,
            is_profitable=net_pnl > 0,
        )

    def evaluate_candidate(
        self,
        underlying: str,
        spot: float,
        strike: float,
        option_type: Literal["CE", "PE"],
        dte_days: float,
        iv: float,
        target_spot: float,
        stop_spot: float,
        quantity: int,
        market_premium: Optional[float] = None,
        expected_fast_hours: float = 0.5,  # 30 mins for scalp/fast intraday
        expected_slow_hours: float = 3.0,  # 3 hours for slower intraday move
    ) -> PathSimulationReport:
        """
        Evaluates a prospective option trade across the 5 canonical scenarios.
        Determines overall economic viability.
        """
        t_years = max(1e-6, dte_days / 365.0)

        # Calculate initial Greeks
        greeks = BlackScholesGreeks.calculate_greeks(
            spot=spot,
            strike=strike,
            time_to_expiry_years=t_years,
            volatility=iv,
            option_type=option_type,
        )
        entry_price = market_premium if market_premium and market_premium > 0 else greeks.theoretical_price

        # 1. Fast Favorable
        fast_scen = self.simulate_path_scenario(
            scenario_name="FAST_FAVORABLE",
            spot_start=spot,
            spot_end=target_spot,
            strike=strike,
            time_to_expiry_start_years=t_years,
            holding_hours=expected_fast_hours,
            iv_start=iv,
            iv_end=iv,
            option_type=option_type,
            quantity=quantity,
            entry_premium=entry_price,
        )

        # 2. Slow Favorable (Target hit after prolonged holding)
        slow_scen = self.simulate_path_scenario(
            scenario_name="SLOW_FAVORABLE",
            spot_start=spot,
            spot_end=target_spot,
            strike=strike,
            time_to_expiry_start_years=t_years,
            holding_hours=expected_slow_hours,
            iv_start=iv,
            iv_end=iv,
            option_type=option_type,
            quantity=quantity,
            entry_premium=entry_price,
        )

        # 3. Sideways (Underlying unchanged over slow horizon)
        sideways_scen = self.simulate_path_scenario(
            scenario_name="SIDEWAYS_BLEED",
            spot_start=spot,
            spot_end=spot,
            strike=strike,
            time_to_expiry_start_years=t_years,
            holding_hours=expected_slow_hours,
            iv_start=iv,
            iv_end=iv,
            option_type=option_type,
            quantity=quantity,
            entry_premium=entry_price,
        )

        # 4. Adverse Stop Loss Hit
        adverse_scen = self.simulate_path_scenario(
            scenario_name="ADVERSE_STOP",
            spot_start=spot,
            spot_end=stop_spot,
            strike=strike,
            time_to_expiry_start_years=t_years,
            holding_hours=expected_fast_hours,
            iv_start=iv,
            iv_end=iv,
            option_type=option_type,
            quantity=quantity,
            entry_premium=entry_price,
        )

        # 5. IV Crush Scenario (Target reached, but IV drops by 20% relative)
        iv_crushed = max(0.05, iv * 0.80)
        iv_crush_scen = self.simulate_path_scenario(
            scenario_name="IV_CRUSH_TARGET",
            spot_start=spot,
            spot_end=target_spot,
            strike=strike,
            time_to_expiry_start_years=t_years,
            holding_hours=expected_slow_hours,
            iv_start=iv,
            iv_end=iv_crushed,
            option_type=option_type,
            quantity=quantity,
            entry_premium=entry_price,
        )

        # Viability Checks
        viability_reasons: list[str] = []
        is_viable = True

        # Criteria 1: Fast target must produce net gain > 1.25x friction
        if fast_scen.net_pnl_total <= 0:
            is_viable = False
            viability_reasons.append("Fast target fails to achieve positive net P&L after friction")
        elif fast_scen.net_pnl_total < fast_scen.friction_total * 1.5:
            is_viable = False
            viability_reasons.append(f"Net profit (₹{fast_scen.net_pnl_total}) is insufficient relative to transaction friction (₹{fast_scen.friction_total})")

        # Criteria 2: Slow target must not be eaten up completely by theta
        if slow_scen.net_pnl_total <= 0:
            is_viable = False
            viability_reasons.append(f"Theta decay over {expected_slow_hours}h wipes out entire target move profit")

        # Criteria 3: Delta cannot be too low for option buyer (avoid extreme OTM lottery tickets)
        if abs(greeks.delta) < 0.25:
            is_viable = False
            viability_reasons.append(f"Option delta ({abs(greeks.delta):.2f}) is too low (< 0.25) to capture underlying move efficiently")

        # Criteria 4: Realistic reward-to-risk in net rupees
        loss_at_stop = abs(adverse_scen.net_pnl_total)
        gain_at_target = fast_scen.net_pnl_total
        realized_rr = (gain_at_target / loss_at_stop) if loss_at_stop > 0 else 0.0
        if realized_rr < 1.20:
            is_viable = False
            viability_reasons.append(f"Realized net Reward/Risk ({realized_rr:.2f}) is below minimum threshold (1.20)")

        if is_viable:
            viability_reasons.append(f"Viable: Realized Net R/R = {realized_rr:.2f} (Target Net: ₹{gain_at_target:,.0f}, Stop Net: ₹{-loss_at_stop:,.0f})")

        return PathSimulationReport(
            underlying=underlying,
            strike=strike,
            option_type=option_type,
            entry_spot=spot,
            entry_premium=entry_price,
            quantity=quantity,
            initial_delta=greeks.delta,
            initial_gamma=greeks.gamma,
            initial_theta_hour=greeks.theta_hour,
            initial_vega=greeks.vega,
            iv=iv,
            dte_days=dte_days,
            fast_target=fast_scen,
            slow_target=slow_scen,
            sideways=sideways_scen,
            adverse_stop=adverse_scen,
            iv_crush_target=iv_crush_scen,
            is_economically_viable=is_viable,
            viability_rationale=viability_reasons,
        )
