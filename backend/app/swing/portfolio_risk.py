"""
Portfolio Risk & Greeks Concentration Guard (v6.0 Options Overhaul).
Guarantees:
  1. Portfolio Heat Ceiling: Total open premium risk <= 5.0% of portfolio equity.
  2. Underlying Concentration: Maximum 2 positions per underlying (prevents single-index overexposure).
  3. Max Position Count: Maximum 6 concurrent swing trades.
  4. Greeks Ceiling & Cross-Horizon Harmonization via PortfolioGreeksLedger.
"""
from __future__ import annotations

from typing import Optional
from app.swing.models import SwingPosition, SwingSetup, PortfolioRiskState
from app.signals.portfolio_greeks import portfolio_greeks_ledger


class PortfolioRiskManager:
    def __init__(
        self,
        total_equity: float = 1_000_000.0,
        max_heat_pct: float = 5.0,
        max_positions_per_underlying: int = 2,
        max_positions_count: int = 6,
    ):
        self.total_equity = total_equity
        self.max_heat_pct = max_heat_pct
        self.max_positions_per_underlying = max_positions_per_underlying
        self.max_positions_count = max_positions_count

    def compute_portfolio_state(self, open_positions: list[SwingPosition]) -> PortfolioRiskState:
        """
        Consolidates open position premium outlay, heat %, and portfolio-wide Greeks.
        """
        total_deployed = sum(p.entry_premium * p.lot_size * p.num_lots for p in open_positions)
        total_risk = sum(
            max(0.0, (p.entry_premium - p.current_stop_premium) * p.lot_size * p.num_lots)
            for p in open_positions
        )
        heat_pct = (total_risk / self.total_equity * 100.0) if self.total_equity > 0 else 0.0

        underlying_counts: dict[str, int] = {}
        for p in open_positions:
            underlying_counts[p.underlying] = underlying_counts.get(p.underlying, 0) + 1

        # Fetch cross-horizon Greeks from central ledger
        ledger_summary = portfolio_greeks_ledger.get_summary()

        return PortfolioRiskState(
            total_equity=self.total_equity,
            total_premium_deployed=round(total_deployed, 2),
            premium_at_risk=round(total_risk, 2),
            portfolio_heat_pct=round(heat_pct, 2),
            max_heat_pct=self.max_heat_pct,
            net_delta=round(ledger_summary.total_delta, 2),
            net_theta_day=round(ledger_summary.total_theta_day, 2),
            net_vega=round(ledger_summary.total_vega, 2),
            open_positions_count=len(open_positions),
            max_positions_count=self.max_positions_count,
            positions_by_underlying=underlying_counts,
            max_positions_per_underlying=self.max_positions_per_underlying,
        )

    def validate_candidate(
        self,
        candidate: SwingSetup,
        open_positions: list[SwingPosition],
        planned_lots: int = 1,
    ) -> tuple[bool, str]:
        """
        Evaluates whether candidate option setup can be safely entered.
        Returns (is_allowed, reason).
        """
        # 1. Maximum concurrent positions
        if len(open_positions) >= self.max_positions_count:
            return False, f"Portfolio reached maximum open position limit ({self.max_positions_count})."

        # 2. Underlying concentration limit (anti-cluster)
        und_count = sum(1 for p in open_positions if p.underlying.upper() == candidate.underlying.upper())
        if und_count >= self.max_positions_per_underlying:
            return False, (
                f"Underlying concentration limit reached for '{candidate.underlying}' "
                f"({und_count}/{self.max_positions_per_underlying} positions). Candidate BLOCKED."
            )

        # 3. Portfolio Heat Check
        curr_risk = sum(
            max(0.0, (p.entry_premium - p.current_stop_premium) * p.lot_size * p.num_lots)
            for p in open_positions
        )
        candidate_risk = candidate.premium_risk_per_lot * planned_lots
        new_heat_pct = ((curr_risk + candidate_risk) / self.total_equity) * 100.0

        if new_heat_pct > self.max_heat_pct:
            return False, (
                f"Entering {candidate.underlying} {candidate.strike} {candidate.option_type} "
                f"would push portfolio heat to {new_heat_pct:.1f}%, exceeding ceiling of {self.max_heat_pct:.1f}%. Candidate BLOCKED."
            )

        # 4. Cross-horizon & Greeks Ceiling Check via PortfolioGreeksLedger
        unit_delta = float(candidate.greeks.get("delta", 0.5))
        unit_gamma = float(candidate.greeks.get("gamma", 0.001))
        unit_theta = float(candidate.greeks.get("theta_day", -5.0))
        unit_vega = float(candidate.greeks.get("vega", 5.0))

        marginal_res = portfolio_greeks_ledger.evaluate_marginal_trade(
            underlying=candidate.underlying,
            horizon="SWING",
            option_type=candidate.option_type,
            strike=candidate.strike,
            expiry_date=candidate.expiry_date,
            quantity=candidate.lot_size * planned_lots,
            unit_delta=unit_delta,
            unit_gamma=unit_gamma,
            unit_theta_day=unit_theta,
            unit_vega=unit_vega,
        )

        if not marginal_res.allowed:
            return False, f"Portfolio Greeks Gate Rejection: {marginal_res.rejection_reason}"

        return True, "Passed all portfolio risk, heat, and Greeks concentration gates."


portfolio_risk_manager = PortfolioRiskManager()

