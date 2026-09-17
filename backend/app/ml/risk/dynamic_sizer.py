"""Dynamic Position Sizing Engine for DROID ML Engine.

Implements Section 19 and Section 20 of the DROID ML Specification.
Applies half-Kelly criterion, calibrated Net EV, and excursion ratios to scale
position size defensibly while respecting Risk Engine absolute maximum caps.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SizingResult:
    recommended_lots: int
    base_lots: int
    max_lots: int
    sizing_multiplier: float
    half_kelly_fraction: float
    is_authorized: bool
    rationale: str


class DynamicPositionSizer:
    """
    Computes volatility, Kelly, and EV-based position scaling.
    Mandate: ML proposes adjustments; Risk Engine sets absolute bounds.
    """

    def __init__(
        self,
        min_multiplier: float = 0.50,
        max_multiplier: float = 1.25,
        drawdown_haircut_threshold: float = 2.0,  # 2% intraday drawdown triggers reduction
        drawdown_severe_threshold: float = 4.0,   # 4% triggers defensive floor
    ):
        self.min_multiplier = min_multiplier
        self.max_multiplier = max_multiplier
        self.drawdown_haircut_threshold = drawdown_haircut_threshold
        self.drawdown_severe_threshold = drawdown_severe_threshold

    def compute_size(
        self,
        base_lots: int,
        max_lots: int,
        calibrated_p_win: float,
        expected_mfe_r: float,
        expected_mae_r: float,
        net_ev_total: float,
        is_ev_viable: bool,
        current_drawdown_pct: float = 0.0,
    ) -> SizingResult:
        """
        Computes dynamic lot allocation.
        """
        # Hard Stop: Non-viable EV immediately rejected
        if not is_ev_viable or net_ev_total <= 0:
            return SizingResult(
                recommended_lots=0,
                base_lots=base_lots,
                max_lots=max_lots,
                sizing_multiplier=0.0,
                half_kelly_fraction=0.0,
                is_authorized=False,
                rationale="REJECT: Non-viable after-cost EV",
            )

        # 1. Kelly calculation
        b = expected_mfe_r / max(0.2, expected_mae_r)  # Win/Loss payoff ratio
        p = min(0.95, max(0.05, calibrated_p_win))
        q = 1.0 - p

        full_kelly = (b * p - q) / max(0.01, b)
        half_kelly = max(0.0, full_kelly * 0.5)

        # 2. Map Half-Kelly to bounded multiplier [0.50, 1.25]
        if half_kelly < 0.08:
            mult = 0.50
        elif half_kelly < 0.18:
            mult = 0.75
        elif half_kelly < 0.32:
            mult = 1.00
        else:
            mult = 1.25

        # 3. Apply drawdown haircut
        dd_note = ""
        if current_drawdown_pct >= self.drawdown_severe_threshold:
            mult = min(mult, 0.50)
            dd_note = f" (severe DD {current_drawdown_pct:.1f}% -> defensive floor 0.5x)"
        elif current_drawdown_pct >= self.drawdown_haircut_threshold:
            mult = round(mult * 0.75, 2)
            dd_note = f" (mild DD {current_drawdown_pct:.1f}% -> haircut 0.75x)"

        # Multiplier bounds
        mult = max(self.min_multiplier, min(self.max_multiplier, mult))

        # 4. Final lots calculation: never exceed max_lots
        scaled_lots = int(round(base_lots * mult))
        final_lots = max(1, min(scaled_lots, max_lots))

        rationale = f"Sizing: {final_lots} lots (base={base_lots}, mult={mult:.2f}, half_kelly={half_kelly:.2f}){dd_note}"

        return SizingResult(
            recommended_lots=final_lots,
            base_lots=base_lots,
            max_lots=max_lots,
            sizing_multiplier=mult,
            half_kelly_fraction=round(half_kelly, 4),
            is_authorized=True,
            rationale=rationale,
        )


dynamic_position_sizer = DynamicPositionSizer()
