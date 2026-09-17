"""
Options Intelligence: Quantitative Strike & Expiry Selection Engine
Implements §23, §25, and §26 of Institutional Options Engine.

P1: 5 strikes x 2 expiries, strike-specific LIVE IV + LIVE per-strike spread,
DTE in hours to 15:30 IST, scoring at SIZED lots from the risk engine,
fail-closed None when nothing is acceptable, OI/spread pre-filter and a
0DTE gamma/charm veto.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field

from app.signals.contract_resolver import INDEX_CONTRACT_CONFIGS, resolve_option_contract, InstrumentMaster
from app.signals.options_intelligence.greeks import BlackScholesGreeks, GreeksResult
from app.signals.options_intelligence.path_simulator import (
    PathDependentOptionSimulator,
    PathSimulationReport,
    IndianOptionCosts,
    VIABILITY_MIN_NET_RR,
)
from app.signals.safety.clocks import IST

# 0DTE veto thresholds: near-expiry gamma/charm explodes — a scalp that holds
# through the last hour is gambling on pin noise.
ZERO_DTE_HOURS = 7.0
ZERO_DTE_GAMMA_VETO = 0.004
ZERO_DTE_CHARM_HOUR_VETO = 0.02
MIN_OI_FOR_SELECTION = 1000


def dte_hours_to_1530_ist(expiry: date, as_of: datetime) -> float:
    """Trading-clock DTE in hours from `as_of` to expiry-day 15:30 IST.

    Date-difference DTE overstates a 0DTE afternoon (3 calendar days vs 2
    trading hours left). The greeks + theta math downstream must see the
    real clock.
    """
    try:
        base = as_of.astimezone(IST) if as_of.tzinfo else as_of.replace(tzinfo=IST)
    except Exception:
        base = as_of
    try:
        close = datetime(expiry.year, expiry.month, expiry.day, 15, 30, tzinfo=IST)
        hrs = (close - base).total_seconds() / 3600.0
        return max(0.25, hrs)
    except Exception:
        return 24.0


def _resolve_two_expiries(underlying: str, ref: date) -> list[date]:
    """Near + next weekly expiries (fail-soft: [near] when the second is unknown)."""
    try:
        from app.signals.contract_resolver import resolve_nearest_expiry
        near, _ = resolve_nearest_expiry(underlying, ref)
        nxt, _ = resolve_nearest_expiry(underlying, near + timedelta(days=1))
        if nxt and nxt != near:
            return [near, nxt]
        return [near]
    except Exception:
        return []


def _live_mark_for(symbol: str) -> Optional[object]:
    try:
        from app.signals.option_marks import option_mark_registry
        return option_mark_registry.get(symbol)
    except Exception:
        return None


class EvaluatedStrikeCandidate(BaseModel):
    strike: float
    strike_type: Literal["DEEP_ITM", "ITM_1", "ATM", "OTM_1", "DEEP_OTM"]
    option_type: Literal["CE", "PE"]
    expiry: Optional[str] = None
    dte_hours: float = 0.0
    greeks: GreeksResult
    theoretical_price: float
    market_premium: float
    live_iv: Optional[float] = None
    spread_pts: float = 1.0
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
    sized_lots: int = 1
    sized_quantity: int = 0
    is_viable: bool = Field(..., description="True only if the selected candidate passed all guards")
    non_viability_reasons: list[str] = Field(default_factory=list)


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
        candidate_types: Optional[list[str]] = None,  # e.g. ["ITM_1", "ATM"] for Intraday Swing MVP
        max_theta_drag_ratio: float = 20.0,  # 20% ceiling as per §12
        min_net_rr: Optional[float] = None,   # defaults to unified 1.20
        max_spread_pct: float = 2.5,          # 2.5% ceiling as per §11
        # ── P1 extensions (all optional for backward compat) ──
        option_chain_quotes_next: Optional[dict[float, float]] = None,
        iv_by_strike: Optional[dict[float, float]] = None,
        spread_by_strike: Optional[dict[float, float]] = None,
        oi_by_strike: Optional[dict[float, float]] = None,
        volume_by_strike: Optional[dict[float, float]] = None,
        lots: int = 1,
        lot_size_override: Optional[int] = None,
        min_oi: float = MIN_OI_FOR_SELECTION,
    ) -> Optional[StrikeSelectionResult]:
        """
        Runs full multi-strike evaluation and returns the best-fit contract.
        Fail-closed: None when no chain-backed acceptable candidate exists —
        never a non-viable "best".
        """
        cfg = INDEX_CONTRACT_CONFIGS.get(underlying)
        if not cfg or spot_price <= 0:
            return None

        # Resolve expected move points and horizon from projection if provided
        if expected_move_projection is not None:
            expected_move_points = getattr(expected_move_projection, "expected_move_points", expected_move_points)
            target_horizon_hours = getattr(expected_move_projection, "expected_duration_hours", target_horizon_hours)

        if expected_move_points is None or expected_move_points <= 0:
            expected_move_points = spot_price * 0.005  # 0.5% baseline fallback

        if min_net_rr is None:
            min_net_rr = VIABILITY_MIN_NET_RR

        step = float(cfg["strike_interval"])
        lot_size = int(lot_size_override or cfg["lot_size"])
        sized_lots = max(1, int(lots or 1))
        sized_qty = sized_lots * lot_size
        opt_type: Literal["CE", "PE"] = "CE" if direction == "LONG_CALL" else "PE"

        # Calculate base ATM strike
        atm_strike = round(spot_price / step) * step

        # Direction-specific target and stop spot levels
        if direction == "LONG_CALL":
            target_spot = spot_price + expected_move_points
            stop_spot = spot_price - stop_loss_points
            raw_candidates = [
                (atm_strike - 2 * step, "DEEP_ITM"),
                (atm_strike - step, "ITM_1"),
                (atm_strike, "ATM"),
                (atm_strike + step, "OTM_1"),
                (atm_strike + 2 * step, "DEEP_OTM"),
            ]
        else:
            target_spot = spot_price - expected_move_points
            stop_spot = spot_price + stop_loss_points
            raw_candidates = [
                (atm_strike + 2 * step, "DEEP_ITM"),
                (atm_strike + step, "ITM_1"),
                (atm_strike, "ATM"),
                (atm_strike - step, "OTM_1"),
                (atm_strike - 2 * step, "DEEP_OTM"),
            ]

        if candidate_types:
            strike_candidates = [c for c in raw_candidates if c[1] in candidate_types]
        else:
            strike_candidates = raw_candidates

        now = as_of_datetime or datetime.now(IST)
        try:
            ref_date = now.date() if isinstance(now.date(), date) else date.today()
        except Exception:
            from datetime import date as _d
            ref_date = _d.today()
        expiries = _resolve_two_expiries(underlying, ref_date)
        if not expiries:
            temp_contract = resolve_option_contract(underlying, Decimal(str(spot_price)), opt_type, strike_offset=0, ref_date=ref_date)
            expiries = [temp_contract.expiry_date] if temp_contract.expiry_date else []

        evaluated_candidates: list[EvaluatedStrikeCandidate] = []
        default_spread_pts = getattr(self.simulator.costs, "default_spread_pts", 1.0)
        default_slip = getattr(self.simulator.costs, "default_slippage_pts", 0.5)

        for expiry_date in expiries:
            dte_hours = dte_hours_to_1530_ist(expiry_date, now)
            # Calendar-time T: wall hours to the 15:30 close over a 365d year.
            t_years = max(1e-6, dte_hours / 8760.0)
            dte_days_cal = max(0.05, dte_hours / 24.0)
            quotes_for_expiry = option_chain_quotes if expiry_date == expiries[0] else (option_chain_quotes_next or {})

            for strike_val, s_type in strike_candidates:
                # ── Live quote resolution (fail-closed per strike) ──
                mkt_price = None
                if quotes_for_expiry and strike_val in quotes_for_expiry:
                    try:
                        mkt_price = float(quotes_for_expiry[strike_val])
                    except Exception:
                        mkt_price = None
                if mkt_price is None or mkt_price <= 0:
                    continue

                # ── Strike-specific live IV (solve per strike, never one global) ──
                live_iv: Optional[float] = None
                try:
                    if iv_by_strike and (strike_val in iv_by_strike or float(strike_val) in iv_by_strike):
                        live_iv = float(iv_by_strike.get(strike_val, iv_by_strike.get(float(strike_val))))
                    if live_iv is None or live_iv <= 0:
                        live_iv = BlackScholesGreeks.solve_iv(mkt_price, spot_price, strike_val, t_years, opt_type)
                    if live_iv is None or live_iv <= 0:
                        live_iv = float(current_iv) if current_iv and float(current_iv) > 0 else None
                except Exception:
                    live_iv = None
                if live_iv is None or live_iv <= 0:
                    continue
                eff_iv = float(live_iv)

                # ── Live per-strike spread (chain mark bid/ask > explicit map > default) ──
                spread_pts = default_spread_pts
                slip_pts = default_slip
                try:
                    if spread_by_strike and (strike_val in spread_by_strike or float(strike_val) in spread_by_strike):
                        spread_pts = float(spread_by_strike.get(strike_val, spread_by_strike.get(float(strike_val), spread_pts)))
                    # Upgrade from the live mark registry when the exact symbol is known.
                    try:
                        probe = resolve_option_contract(
                            underlying, Decimal(str(spot_price)), opt_type,
                            strike_offset=0, ref_date=ref_date, exact_strike=strike_val,
                        )
                        mk = _live_mark_for(getattr(probe, "broker_symbol", "") or "")
                        if mk is not None and getattr(mk, "spread_pts", None):
                            spread_pts = float(mk.spread_pts)  # type: ignore[arg-type]
                    except Exception:
                        pass
                except Exception:
                    pass

                # ── OI / spread pre-filter (unknown liquidity passes; known-bad is cut) ──
                try:
                    oi_v = None
                    if oi_by_strike and (strike_val in oi_by_strike or float(strike_val) in oi_by_strike):
                        oi_v = float(oi_by_strike.get(strike_val, oi_by_strike.get(float(strike_val), 0)) or 0)
                    if oi_v is not None and oi_v > 0 and oi_v < float(min_oi or 0):
                        continue
                except Exception:
                    pass

                # Greeks calculation (per-strike IV, hour-precision T).
                greeks = BlackScholesGreeks.calculate_greeks(
                    spot=spot_price,
                    strike=strike_val,
                    time_to_expiry_years=t_years,
                    volatility=eff_iv,
                    option_type=opt_type,
                )

                # 0DTE gamma/charm veto: last-hour delta shape is untradeable.
                if dte_hours <= ZERO_DTE_HOURS:
                    try:
                        g = abs(float(greeks.gamma or 0.0))
                        ch = abs(float(getattr(greeks, "charm_hour", 0.0) or 0.0))
                        if g > ZERO_DTE_GAMMA_VETO or ch > ZERO_DTE_CHARM_HOUR_VETO:
                            evaluated_candidates.append(
                                EvaluatedStrikeCandidate(
                                    strike=strike_val, strike_type=s_type,  # type: ignore
                                    option_type=opt_type,
                                    expiry=expiry_date.isoformat(),
                                    dte_hours=round(dte_hours, 2),
                                    greeks=greeks,
                                    theoretical_price=greeks.theoretical_price,
                                    market_premium=round(mkt_price, 2),
                                    live_iv=round(eff_iv, 4),
                                    spread_pts=round(float(spread_pts), 2),
                                    theta_drag_ratio=100.0,
                                    spread_friction_pct=100.0,
                                    net_rr_ratio=0.0,
                                    score=0.0,
                                    simulation_report=self.simulator.evaluate_candidate(
                                        underlying=underlying, spot=spot_price, strike=strike_val,
                                        option_type=opt_type, dte_days=dte_days_cal,
                                        iv=eff_iv, target_spot=target_spot, stop_spot=stop_spot,
                                        quantity=sized_qty, market_premium=mkt_price,
                                        expected_fast_hours=max(0.25, target_horizon_hours * 0.5),
                                        expected_slow_hours=max(1.0, target_horizon_hours * 1.5),
                                        spread_pts=float(spread_pts), slippage_pts=float(slip_pts),
                                    ),
                                    rejection_reasons=[f"0DTE_GAMMA_CHARM_VETO: gamma={g:.4f} charm/h={ch:.4f} with {dte_hours:.1f}h to close"],
                                    is_acceptable=False,
                                )
                            )
                            continue
                    except Exception:
                        pass

                # Run path-dependent simulation at SIZED qty.
                sim_report = self.simulator.evaluate_candidate(
                    underlying=underlying,
                    spot=spot_price,
                    strike=strike_val,
                    option_type=opt_type,
                    dte_days=dte_days_cal,
                    iv=eff_iv,
                    target_spot=target_spot,
                    stop_spot=stop_spot,
                    quantity=sized_qty,
                    market_premium=mkt_price,
                    expected_fast_hours=max(0.25, target_horizon_hours * 0.5),
                    expected_slow_hours=max(1.0, target_horizon_hours * 1.5),
                    spread_pts=float(spread_pts),
                    slippage_pts=float(slip_pts),
                )

                # Metrics
                expected_gross_gain = abs(sim_report.fast_target.gross_pnl_per_share)
                theta_hr = abs(greeks.theta_hour)
                theta_drag_ratio = (theta_hr * target_horizon_hours / expected_gross_gain * 100.0) if expected_gross_gain > 0 else 100.0
                spread_friction = (sim_report.fast_target.friction_total / (expected_gross_gain * sized_qty) * 100.0) if expected_gross_gain > 0 else 100.0
                spread_pct = (spread_pts / mkt_price * 100.0) if mkt_price > 0 else 0.0
                net_rr = (sim_report.fast_target.net_pnl_total / abs(sim_report.adverse_stop.net_pnl_total)) if sim_report.adverse_stop.net_pnl_total < 0 else 0.0

                rejection_reasons = []
                # Guard 1: Minimum Delta
                if abs(greeks.delta) < 0.35:
                    rejection_reasons.append(f"Delta ({abs(greeks.delta):.2f}) is too low (< 0.35)")

                # Guard 2: Theta drag ceiling (§12)
                if theta_drag_ratio > max_theta_drag_ratio:
                    rejection_reasons.append(f"Theta drag ({theta_drag_ratio:.1f}%) exceeds {max_theta_drag_ratio:.0f}% ceiling")

                # Guard 3: Option bid-ask spread ceiling (§11: max 2.5% of premium)
                if max_spread_pct is not None and spread_pct > max_spread_pct:
                    rejection_reasons.append(f"Spread ({spread_pct:.1f}%) exceeds {max_spread_pct:.1f}% ceiling")

                # Guard 4: Net R/R minimum (unified 1.20)
                if min_net_rr is not None and net_rr < min_net_rr:
                    rejection_reasons.append(f"Net R/R ({net_rr:.2f}) below minimum required ({min_net_rr:.1f})")

                # Guard 5: Economic viability from simulator
                if not sim_report.is_economically_viable:
                    rejection_reasons.extend(sim_report.viability_rationale)

                is_acceptable = len(rejection_reasons) == 0

                # Scoring algorithm (0 to 100)
                score = 50.0
                score += min(25.0, abs(greeks.delta) * 35.0)

                abs_delta = abs(greeks.delta)
                if 0.55 <= abs_delta <= 0.75:
                    score += 5.0
                if 0.60 <= abs_delta <= 0.70:
                    score += 5.0

                score += min(20.0, net_rr * 8.0)
                score -= min(25.0, theta_drag_ratio * 0.8)
                score -= min(15.0, spread_friction * 0.5)
                score = max(0.0, min(100.0, round(score, 1)))

                evaluated_candidates.append(
                    EvaluatedStrikeCandidate(
                        strike=strike_val,
                        strike_type=s_type,  # type: ignore
                        option_type=opt_type,
                        expiry=expiry_date.isoformat(),
                        dte_hours=round(dte_hours, 2),
                        greeks=greeks,
                        theoretical_price=greeks.theoretical_price,
                        market_premium=round(mkt_price, 2),
                        live_iv=round(eff_iv, 4),
                        spread_pts=round(float(spread_pts), 2),
                        theta_drag_ratio=round(theta_drag_ratio, 2),
                        spread_friction_pct=round(spread_friction, 2),
                        net_rr_ratio=round(net_rr, 2),
                        score=score if is_acceptable else score * 0.5,
                        simulation_report=sim_report,
                        rejection_reasons=rejection_reasons,
                        is_acceptable=is_acceptable,
                    )
                )

        # Fail-closed: no chain-backed candidates at all = no selection.
        if not evaluated_candidates:
            return None
        acceptable_candidates = [c for c in evaluated_candidates if c.is_acceptable]
        if not acceptable_candidates:
            # Never return a non-viable "best" — the desk stands down.
            return None
        best_candidate = max(acceptable_candidates, key=lambda c: c.score)

        # Map to InstrumentMaster contract (resolve exact strike on the winning expiry).
        try:
            win_expiry = date.fromisoformat(best_candidate.expiry) if best_candidate.expiry else ref_date
        except Exception:
            win_expiry = ref_date
        # Nearest-expiry resolver may not land on the winning (next-week) expiry;
        # resolve against the winning expiry's week then pin the exact strike.
        try:
            final_contract = resolve_option_contract(
                underlying=underlying,
                spot_price=Decimal(str(spot_price)),
                option_type=opt_type,
                strike_offset=0,
                ref_date=win_expiry,
                exact_strike=best_candidate.strike,
            )
        except Exception:
            final_contract = resolve_option_contract(
                underlying=underlying,
                spot_price=Decimal(str(spot_price)),
                option_type=opt_type,
                strike_offset=0,
                ref_date=ref_date,
                exact_strike=best_candidate.strike,
            )
        # Propagate the chain quote that priced this candidate onto the contract.
        try:
            if (final_contract.live_premium is None or float(final_contract.live_premium) <= 0) and best_candidate.market_premium > 0:
                final_contract.live_premium = float(best_candidate.market_premium)
                if str(getattr(final_contract, "contract_source", "")).lower() != "fyers_chain":
                    final_contract.contract_source = "chain_quotes"
        except Exception:
            pass

        rationale = [
            f"Selected {best_candidate.strike_type} ({best_candidate.strike}) {best_candidate.expiry} with score {best_candidate.score}/100",
            f"Delta: {best_candidate.greeks.delta:.2f}, Gamma: {best_candidate.greeks.gamma:.4f}, Vega: {best_candidate.greeks.vega:.2f}",
            f"Theta decay: ₹{abs(best_candidate.greeks.theta_hour):.2f}/hr ({best_candidate.theta_drag_ratio:.1f}% of target profit)",
            f"Simulated Net R/R: {best_candidate.net_rr_ratio:.2f} after statutory taxes & execution friction",
            f"Sized at {sized_lots} lot(s) x {lot_size} = {sized_qty} qty; live IV {best_candidate.live_iv} spread ₹{best_candidate.spread_pts}",
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
            sized_lots=sized_lots,
            sized_quantity=sized_qty,
            is_viable=True,
            non_viability_reasons=[],
        )


# Global singleton
quantitative_contract_selector = QuantitativeContractSelector()
