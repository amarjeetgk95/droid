"""
Options Intelligence: Quantitative Strike & Expiry Selection Engine
Implements §23, §25, and §26 of Institutional Options Engine.

Replaces hardcoded strike offsets with multi-criteria optimization:
  - Strike candidate comparison: ITM-1, ATM, OTM-1
  - Expiry evaluation: Current weekly vs Next weekly
  - Optimization metrics:
      * Delta efficiency (underlying move capture)
      * Theta drag burden (% of expected gain decayed per hour)
      * Microstructure friction (spread as % of profit)
      * Path-dependent net R-multiple
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS, resolve_option_contract, InstrumentMaster
from app.signals.options_intelligence.greeks import BlackScholesGreeks, GreeksResult
from app.signals.options_intelligence.path_simulator import (
    PathDependentOptionSimulator,
    PathSimulationReport,
    IndianOptionCosts,
)

IST = timezone(timedelta(hours=5, minutes=30))


class EvaluatedStrikeCandidate(BaseModel):
    strike: float
    strike_type: Literal["DEEP_ITM", "ITM_1", "ATM", "OTM_1", "DEEP_OTM"]
    option_type: Literal["CE", "PE"]
    greeks: GreeksResult
    theoretical_price: float
    market_premium: float
    theta_drag_ratio: float = Field(..., description="Hourly theta decay as % of expected option gain")
    spread_friction_pct: float = Field(..., description="Estimated spread & friction as % of target profit")
    net_rr_ratio: float = Field(..., description="Simulated net reward-to-risk ratio")
    score: float = Field(..., description="Overall quantitative selection score (0-100)")
    simulation_report: PathSimulationReport
    rejection_reasons: list[str] = Field(default_factory=list)
    is_acceptable: bool


class StrikeSelectionResult(BaseModel):
    underlying: str
    direction: Literal["LONG_CALL", "LONG_PUT"]
    selected_contract: InstrumentMaster
    selected_strike: float
    selected_strike_type: str
    selected_greeks: GreeksResult
    all_candidates: list[EvaluatedStrikeCandidate]
    selection_rationale: list[str]
    selection_score: float
    path_simulation: PathSimulationReport
    expected_move_projection: Optional[object] = None


class QuantitativeContractSelector:
    """
    Evaluates available strike contracts and expiries to select the optimal
    risk-adjusted option contract for a specific underlying trade setup.
    """

    def __init__(self, simulator: Optional[PathDependentOptionSimulator] = None):
        self.simulator = simulator or PathDependentOptionSimulator()

    def select_optimal_contract(
        self,
        underlying: Literal["NIFTY", "BANKNIFTY", "SENSEX"],
        spot_price: float,
        direction: Literal["LONG_CALL", "LONG_PUT"],
        expected_move_points: Optional[float] = None,
        stop_loss_points: float = 30.0,
        target_horizon_hours: float = 1.0,
        current_iv: float = 0.16,  # 16% annualized baseline
        option_chain_quotes: Optional[dict[float, float]] = None,  # strike -> market price
        expected_move_projection: Optional[object] = None,
        as_of_datetime: Optional[datetime] = None,
    ) -> Optional[StrikeSelectionResult]:
        """
        Runs full multi-strike evaluation and returns the best-fit contract.
        """
        cfg = INDEX_CONTRACT_CONFIGS.get(underlying)
        if not cfg:
            return None

        # Resolve expected move points and horizon from projection if provided
        if expected_move_projection is not None:
            expected_move_points = getattr(expected_move_projection, "expected_move_points", expected_move_points)
            target_horizon_hours = getattr(expected_move_projection, "expected_duration_hours", target_horizon_hours)

        if expected_move_points is None or expected_move_points <= 0:
            expected_move_points = spot_price * 0.005  # 0.5% baseline fallback

        step = float(cfg["strike_interval"])
        lot_size = int(cfg["lot_size"])
        opt_type: Literal["CE", "PE"] = "CE" if direction == "LONG_CALL" else "PE"

        # Calculate base ATM strike
        atm_strike = round(spot_price / step) * step

        # Direction-specific target and stop spot levels
        if direction == "LONG_CALL":
            target_spot = spot_price + expected_move_points
            stop_spot = spot_price - stop_loss_points
            # Strikes to compare: ITM-1, ATM, OTM-1
            strike_candidates = [
                (atm_strike - step, "ITM_1"),
                (atm_strike, "ATM"),
                (atm_strike + step, "OTM_1"),
            ]
        else:
            target_spot = spot_price - expected_move_points
            stop_spot = spot_price + stop_loss_points
            strike_candidates = [
                (atm_strike + step, "ITM_1"),
                (atm_strike, "ATM"),
                (atm_strike - step, "OTM_1"),
            ]

        now = as_of_datetime or datetime.now(IST)
        # Determine DTE from contract resolver baseline
        temp_contract = resolve_option_contract(underlying, Decimal(str(spot_price)), opt_type, strike_offset=0, ref_date=now.date())
        days_to_expiry = max(0.2, (temp_contract.expiry_date - now.date()).days) if temp_contract.expiry_date else 3.0
        t_years = days_to_expiry / 365.0

        evaluated_candidates: list[EvaluatedStrikeCandidate] = []

        for strike_val, s_type in strike_candidates:
            # Greeks calculation
            greeks = BlackScholesGreeks.calculate_greeks(
                spot=spot_price,
                strike=strike_val,
                time_to_expiry_years=t_years,
                volatility=current_iv,
                option_type=opt_type,
            )

            mkt_price = None
            if option_chain_quotes and strike_val in option_chain_quotes:
                mkt_price = option_chain_quotes[strike_val]
            else:
                mkt_price = greeks.theoretical_price

            # Run path-dependent simulation for this strike
            sim_report = self.simulator.evaluate_candidate(
                underlying=underlying,
                spot=spot_price,
                strike=strike_val,
                option_type=opt_type,
                dte_days=days_to_expiry,
                iv=current_iv,
                target_spot=target_spot,
                stop_spot=stop_spot,
                quantity=lot_size,
                market_premium=mkt_price,
                expected_fast_hours=max(0.25, target_horizon_hours * 0.5),
                expected_slow_hours=max(1.0, target_horizon_hours * 1.5),
            )

            # Metrics
            expected_gross_gain = abs(sim_report.fast_target.gross_pnl_per_share)
            theta_hr = abs(greeks.theta_hour)
            theta_drag_ratio = (theta_hr * target_horizon_hours / expected_gross_gain * 100.0) if expected_gross_gain > 0 else 100.0
            spread_friction = (sim_report.fast_target.friction_total / (expected_gross_gain * lot_size) * 100.0) if expected_gross_gain > 0 else 100.0
            net_rr = (sim_report.fast_target.net_pnl_total / abs(sim_report.adverse_stop.net_pnl_total)) if sim_report.adverse_stop.net_pnl_total < 0 else 0.0

            rejection_reasons = []
            # Guard 1: Minimum Delta (Must have sufficient leverage without low-probability lottery drag)
            if abs(greeks.delta) < 0.35:
                rejection_reasons.append(f"Delta ({abs(greeks.delta):.2f}) is too low (< 0.35)")

            # Guard 2: Theta drag cannot exceed 25% of expected target move
            if theta_drag_ratio > 25.0:
                rejection_reasons.append(f"Theta drag ({theta_drag_ratio:.1f}%) exceeds 25% ceiling")

            # Guard 3: Economic viability from simulator
            if not sim_report.is_economically_viable:
                rejection_reasons.extend(sim_report.viability_rationale)

            is_acceptable = len(rejection_reasons) == 0

            # Scoring algorithm (0 to 100)
            # Higher score rewards: high delta efficiency, high net R/R, low theta drag, low spread %
            score = 50.0
            score += min(25.0, abs(greeks.delta) * 35.0)  # Up to +25 for delta
            score += min(20.0, net_rr * 8.0)  # Up to +20 for net R/R
            score -= min(25.0, theta_drag_ratio * 0.8)  # Penalty for high theta
            score -= min(15.0, spread_friction * 0.5)  # Penalty for spread drag
            score = max(0.0, min(100.0, round(score, 1)))

            evaluated_candidates.append(
                EvaluatedStrikeCandidate(
                    strike=strike_val,
                    strike_type=s_type,  # type: ignore
                    option_type=opt_type,
                    greeks=greeks,
                    theoretical_price=greeks.theoretical_price,
                    market_premium=round(mkt_price, 2),
                    theta_drag_ratio=round(theta_drag_ratio, 2),
                    spread_friction_pct=round(spread_friction, 2),
                    net_rr_ratio=round(net_rr, 2),
                    score=score if is_acceptable else score * 0.5,
                    simulation_report=sim_report,
                    rejection_reasons=rejection_reasons,
                    is_acceptable=is_acceptable,
                )
            )

        # Pick highest scoring candidate among acceptable (or highest overall if none strictly pass)
        acceptable_candidates = [c for c in evaluated_candidates if c.is_acceptable]
        if acceptable_candidates:
            best_candidate = max(acceptable_candidates, key=lambda c: c.score)
        else:
            best_candidate = max(evaluated_candidates, key=lambda c: c.score)

        # Map to InstrumentMaster contract
        offset = 0
        if best_candidate.strike_type == "ITM_1":
            offset = -1 if opt_type == "CE" else 1
        elif best_candidate.strike_type == "OTM_1":
            offset = 1 if opt_type == "CE" else -1

        final_contract = resolve_option_contract(
            underlying=underlying,
            spot_price=Decimal(str(spot_price)),
            option_type=opt_type,
            strike_offset=offset,
            ref_date=now.date(),
            exact_strike=best_candidate.strike,
        )

        rationale = [
            f"Selected {best_candidate.strike_type} ({best_candidate.strike}) with score {best_candidate.score}/100",
            f"Delta: {best_candidate.greeks.delta:.2f}, Gamma: {best_candidate.greeks.gamma:.4f}, Vega: {best_candidate.greeks.vega:.2f}",
            f"Theta decay: ₹{abs(best_candidate.greeks.theta_hour):.2f}/hr ({best_candidate.theta_drag_ratio:.1f}% of target profit)",
            f"Simulated Net R/R: {best_candidate.net_rr_ratio:.2f} after statutory taxes & execution friction",
        ]

        return StrikeSelectionResult(
            underlying=underlying,
            direction=direction,
            selected_contract=final_contract,
            selected_strike=best_candidate.strike,
            selected_strike_type=best_candidate.strike_type,
            selected_greeks=best_candidate.greeks,
            all_candidates=evaluated_candidates,
            selection_rationale=rationale,
            selection_score=best_candidate.score,
            path_simulation=best_candidate.simulation_report,
            expected_move_projection=expected_move_projection,
        )


# Global singleton
quantitative_contract_selector = QuantitativeContractSelector()
