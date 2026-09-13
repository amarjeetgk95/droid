"""
Portfolio Risk & Concentration Guard (v5.0 §15, §16, §17).
Guarantees:
  1. Portfolio Heat Ceiling: Total open risk <= 5.0% of portfolio equity.
  2. Sector Concentration: Maximum 2 positions per sector (prevents 5-bank cluster risk).
  3. Max Position Count: Maximum 6 concurrent swing trades.
"""
from __future__ import annotations

from app.swing.models import SwingPosition, SwingSetup, PortfolioRiskState


class PortfolioRiskManager:
    def __init__(
        self,
        total_equity: float = 1_000_000.0,
        max_heat_pct: float = 5.0,
        max_positions_per_sector: int = 2,
        max_positions_count: int = 6,
    ):
        self.total_equity = total_equity
        self.max_heat_pct = max_heat_pct
        self.max_positions_per_sector = max_positions_per_sector
        self.max_positions_count = max_positions_count

    def compute_portfolio_state(self, open_positions: list[SwingPosition]) -> PortfolioRiskState:
        open_cap = sum(p.quantity * p.current_price for p in open_positions)
        # Open risk = sum(quantity * (entry_price - initial_stop))
        open_risk = sum(max(0.0, p.quantity * (p.entry_price - p.initial_stop)) for p in open_positions)
        heat_pct = (open_risk / self.total_equity * 100.0) if self.total_equity > 0 else 0.0

        sector_counts: dict[str, int] = {}
        for p in open_positions:
            sector_counts[p.sector] = sector_counts.get(p.sector, 0) + 1

        return PortfolioRiskState(
            total_equity=self.total_equity,
            open_capital=round(open_cap, 2),
            open_risk_capital=round(open_risk, 2),
            portfolio_heat_pct=round(heat_pct, 2),
            max_heat_pct=self.max_heat_pct,
            sector_allocations=sector_counts,
            open_positions_count=len(open_positions),
            max_positions_count=self.max_positions_count,
        )

    def validate_candidate(
        self,
        candidate: SwingSetup,
        open_positions: list[SwingPosition],
    ) -> tuple[bool, str]:
        """
        Evaluates whether candidate setup can be safely entered.
        Returns (is_allowed, reason).
        """
        # 1. Duplicate symbol check
        if any(p.symbol == candidate.symbol for p in open_positions):
            return False, f"Symbol {candidate.symbol} already has an active open swing position."

        # 2. Maximum concurrent positions
        if len(open_positions) >= self.max_positions_count:
            return False, f"Portfolio reached maximum position limit ({self.max_positions_count})."

        # 3. Sector concentration limit (anti-cluster)
        sector_count = sum(1 for p in open_positions if p.sector.lower() == candidate.sector.lower())
        if sector_count >= self.max_positions_per_sector:
            return False, (
                f"Sector concentration limit reached for '{candidate.sector}' "
                f"({sector_count}/{self.max_positions_per_sector} positions). Candidate BLOCKED."
            )

        # 4. Portfolio Heat Check
        curr_risk = sum(max(0.0, p.quantity * (p.entry_price - p.initial_stop)) for p in open_positions)
        candidate_risk = candidate.risk_per_share * int((self.total_equity * 0.01) / candidate.risk_per_share)
        new_heat_pct = ((curr_risk + candidate_risk) / self.total_equity) * 100.0

        if new_heat_pct > self.max_heat_pct:
            return False, (
                f"Entering {candidate.symbol} would push portfolio heat to {new_heat_pct:.1f}%, "
                f"exceeding ceiling of {self.max_heat_pct:.1f}%. Candidate BLOCKED."
            )

        return True, "Passed all portfolio risk and concentration gates."


portfolio_risk_manager = PortfolioRiskManager()
