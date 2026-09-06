"""
Shared Portfolio Greeks Ledger & Cross-Horizon Harmonizer (§36, §51)
Enforces:
  - Consolidated multi-horizon Greeks ledger across SCALP, INTRADAY, SWING, POSITIONAL.
  - Tracking of aggregate portfolio Delta (ΣΔ), Gamma (ΣΓ), Theta (ΣΘ), Vega (ΣV).
  - Cross-Horizon Harmonization: Recognizes that multiple horizons in the same instrument
    represent correlated directional exposure, preventing compounding leverage.
  - Pre-trade marginal Greek simulation and concentration ceilings.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

TradingHorizon = Literal["SCALP", "INTRADAY", "SWING", "POSITIONAL"]


class PortfolioGreekPosition(BaseModel):
    position_id: str
    underlying: str
    horizon: TradingHorizon
    option_type: Literal["CE", "PE"]
    strike: float
    expiry_date: str
    quantity: int
    unit_delta: float
    unit_gamma: float
    unit_theta_day: float
    unit_vega: float

    @property
    def total_delta(self) -> float:
        return round(self.unit_delta * self.quantity, 2)

    @property
    def total_gamma(self) -> float:
        return round(self.unit_gamma * self.quantity, 4)

    @property
    def total_theta_day(self) -> float:
        return round(self.unit_theta_day * self.quantity, 2)

    @property
    def total_vega(self) -> float:
        return round(self.unit_vega * self.quantity, 2)


class PortfolioGreeksSummary(BaseModel):
    total_delta: float = 0.0
    total_gamma: float = 0.0
    total_theta_day: float = 0.0
    total_vega: float = 0.0
    net_exposure_by_underlying: dict[str, float] = Field(default_factory=dict)
    positions_by_horizon: dict[str, int] = Field(default_factory=dict)
    expiry_concentrations: dict[str, float] = Field(default_factory=dict)
    total_open_positions: int = 0


class MarginalGreekCheckResult(BaseModel):
    allowed: bool
    rejection_reason: Optional[str] = None
    marginal_delta: float
    marginal_gamma: float
    marginal_theta_day: float
    marginal_vega: float
    projected_total_delta: float
    projected_total_theta_day: float
    cross_horizon_overlap_detected: bool = False
    warning_notes: list[str] = Field(default_factory=list)


class PortfolioRiskLimits(BaseModel):
    max_net_delta_per_underlying: float = 350.0  # Max ~5 lots ATM NIFTY delta
    max_portfolio_theta_day_rupees: float = 15000.0  # Max ₹15,000/day total theta burn
    max_expiry_concentration_pct: float = 70.0  # No more than 70% in single expiry
    max_same_direction_horizons: int = 2  # Max 2 horizons in same direction without hedge


class PortfolioGreeksLedger:
    """
    Central shared ledger maintaining aggregate Greek risk across all horizons (§36, §51).
    """

    def __init__(self, limits: Optional[PortfolioRiskLimits] = None):
        self.limits = limits or PortfolioRiskLimits()
        self._positions: dict[str, PortfolioGreekPosition] = {}

    def clear(self) -> None:
        """Reset ledger (primarily for testing)."""
        self._positions.clear()

    def add_position(self, position: PortfolioGreekPosition) -> None:
        self._positions[position.position_id] = position
        logger.info(
            "portfolio_greek_position_added",
            position_id=position.position_id,
            underlying=position.underlying,
            horizon=position.horizon,
            delta=position.total_delta,
            theta=position.total_theta_day,
        )

    def remove_position(self, position_id: str) -> Optional[PortfolioGreekPosition]:
        return self._positions.pop(position_id, None)

    def get_summary(self) -> PortfolioGreeksSummary:
        total_delta = 0.0
        total_gamma = 0.0
        total_theta = 0.0
        total_vega = 0.0
        by_und: dict[str, float] = {}
        by_horiz: dict[str, int] = {}
        by_exp: dict[str, int] = {}

        for p in self._positions.values():
            total_delta += p.total_delta
            total_gamma += p.total_gamma
            total_theta += p.total_theta_day
            total_vega += p.total_vega

            by_und[p.underlying] = round(by_und.get(p.underlying, 0.0) + p.total_delta, 2)
            by_horiz[p.horizon] = by_horiz.get(p.horizon, 0) + 1
            by_exp[p.expiry_date] = by_exp.get(p.expiry_date, 0) + p.quantity

        total_qty = sum(by_exp.values())
        exp_pct = {k: round(v / total_qty * 100.0, 1) for k, v in by_exp.items()} if total_qty > 0 else {}

        return PortfolioGreeksSummary(
            total_delta=round(total_delta, 2),
            total_gamma=round(total_gamma, 4),
            total_theta_day=round(total_theta, 2),
            total_vega=round(total_vega, 2),
            net_exposure_by_underlying=by_und,
            positions_by_horizon=by_horiz,
            expiry_concentrations=exp_pct,
            total_open_positions=len(self._positions),
        )

    def evaluate_marginal_trade(
        self,
        underlying: str,
        horizon: TradingHorizon,
        option_type: Literal["CE", "PE"],
        strike: float,
        expiry_date: str,
        quantity: int,
        unit_delta: float,
        unit_gamma: float,
        unit_theta_day: float,
        unit_vega: float,
    ) -> MarginalGreekCheckResult:
        """
        Simulates the marginal impact of adding a proposed trade on the consolidated portfolio.
        Enforces cross-horizon compounding guards (§51) and Greek risk ceilings (§36).
        """
        current = self.get_summary()

        marginal_delta = round(unit_delta * quantity, 2)
        marginal_gamma = round(unit_gamma * quantity, 4)
        marginal_theta = round(unit_theta_day * quantity, 2)
        marginal_vega = round(unit_vega * quantity, 2)

        proj_delta = round(current.total_delta + marginal_delta, 2)
        proj_theta = round(current.total_theta_day + marginal_theta, 2)

        und_current_delta = current.net_exposure_by_underlying.get(underlying, 0.0)
        proj_und_delta = abs(und_current_delta + marginal_delta)

        warnings: list[str] = []
        overlap_detected = False

        # 1. Cross-Horizon Compounding Exposure Guard (§51)
        # Check how many existing positions in this underlying share the same direction
        same_dir_horizons = [
            p.horizon
            for p in self._positions.values()
            if p.underlying == underlying and p.option_type == option_type
        ]
        if same_dir_horizons:
            overlap_detected = True
            warnings.append(
                f"Cross-horizon overlap: {underlying} {option_type} already active in {', '.join(same_dir_horizons)}. Aggregating directional exposure."
            )
            if len(set(same_dir_horizons)) >= self.limits.max_same_direction_horizons:
                return MarginalGreekCheckResult(
                    allowed=False,
                    rejection_reason=(
                        f"CROSS_HORIZON_LIMIT_EXCEEDED: Maximum of {self.limits.max_same_direction_horizons} "
                        f"concurrent {option_type} positions reached for {underlying} across horizons."
                    ),
                    marginal_delta=marginal_delta,
                    marginal_gamma=marginal_gamma,
                    marginal_theta_day=marginal_theta,
                    marginal_vega=marginal_vega,
                    projected_total_delta=proj_delta,
                    projected_total_theta_day=proj_theta,
                    cross_horizon_overlap_detected=True,
                    warning_notes=warnings,
                )

        # 2. Portfolio Delta Ceiling
        if proj_und_delta > self.limits.max_net_delta_per_underlying:
            return MarginalGreekCheckResult(
                allowed=False,
                rejection_reason=(
                    f"PORTFOLIO_DELTA_BREACH: Projected net delta ({proj_und_delta:.1f}) exceeds "
                    f"ceiling ({self.limits.max_net_delta_per_underlying:.1f}) for {underlying}."
                ),
                marginal_delta=marginal_delta,
                marginal_gamma=marginal_gamma,
                marginal_theta_day=marginal_theta,
                marginal_vega=marginal_vega,
                projected_total_delta=proj_delta,
                projected_total_theta_day=proj_theta,
                cross_horizon_overlap_detected=overlap_detected,
                warning_notes=warnings,
            )

        # 3. Portfolio Daily Theta Burn Ceiling
        if abs(proj_theta) > self.limits.max_portfolio_theta_day_rupees:
            return MarginalGreekCheckResult(
                allowed=False,
                rejection_reason=(
                    f"PORTFOLIO_THETA_BREACH: Projected daily theta decay (₹{abs(proj_theta):,.0f}) exceeds "
                    f"maximum portfolio tolerance (₹{self.limits.max_portfolio_theta_day_rupees:,.0f}/day)."
                ),
                marginal_delta=marginal_delta,
                marginal_gamma=marginal_gamma,
                marginal_theta_day=marginal_theta,
                marginal_vega=marginal_vega,
                projected_total_delta=proj_delta,
                projected_total_theta_day=proj_theta,
                cross_horizon_overlap_detected=overlap_detected,
                warning_notes=warnings,
            )

        return MarginalGreekCheckResult(
            allowed=True,
            marginal_delta=marginal_delta,
            marginal_gamma=marginal_gamma,
            marginal_theta_day=marginal_theta,
            marginal_vega=marginal_vega,
            projected_total_delta=proj_delta,
            projected_total_theta_day=proj_theta,
            cross_horizon_overlap_detected=overlap_detected,
            warning_notes=warnings,
        )


# Global singleton
portfolio_greeks_ledger = PortfolioGreeksLedger()
