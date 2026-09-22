"""
Multi-Factor Signal Scoring Engine (§24).

Combines structural relevance, momentum, directional pressure, translation efficiency,
liquidity vacuum, market regime, and ML validation into a transparent [0, 1] confidence score.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import (
    StructuralLevel,
    VortexFeatureSnapshot,
)


class ScoringWeights(BaseModel):
    """Configurable multi-factor weights (§24)."""
    structural: float = 0.20
    momentum: float = 0.15
    pressure: float = 0.15
    translation: float = 0.15
    liquidity: float = 0.15
    regime: float = 0.10
    ml_validation: float = 0.10


class SignalScoreEngine:
    """Calculates composite signal confidence."""

    def __init__(self, weights: Optional[ScoringWeights] = None) -> None:
        self.weights = weights or ScoringWeights()

    def compute_score(
        self,
        snapshot: VortexFeatureSnapshot,
        interacted_level: Optional[StructuralLevel] = None,
        ml_probability: Optional[float] = None,
    ) -> float:
        """Compute final calibrated signal confidence score in [0, 1].

        Args:
            snapshot: Microstructure feature snapshot.
            interacted_level: The structural level associated with the trigger.
            ml_probability: Optional output from ML validator.

        Returns:
            Normalized signal confidence in [0.0, 1.0].
        """
        w = self.weights

        # 1. Structural score (20%)
        struct_score = interacted_level.relevance_score if interacted_level else 0.50

        # 2. Momentum score (15%)
        # Proxied by snap energy and range expansion
        mom_score = (snapshot.snap_energy.snap_energy + min(snapshot.vacuum.range_expansion / 2.0, 1.0)) / 2.0

        # 3. Pressure score (15%)
        press_score = abs(snapshot.pressure.pressure_score)

        # 4. Translation score (15%)
        trans_score = snapshot.translation.translation_score

        # 5. Liquidity score (15%)
        liq_score = snapshot.vacuum.liquidity_vacuum_score

        # 6. Regime score (10%)
        reg_score = snapshot.regime.regime_confidence

        # 7. ML validation score (10%)
        ml_score = ml_probability if ml_probability is not None else 0.50

        raw_score = (
            w.structural * struct_score
            + w.momentum * mom_score
            + w.pressure * press_score
            + w.translation * trans_score
            + w.liquidity * liq_score
            + w.regime * reg_score
            + w.ml_validation * ml_score
        )

        return round(max(0.0, min(1.0, raw_score)), 4)
