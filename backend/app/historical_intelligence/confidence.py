"""
Historical Confidence Scoring Engine — §22
Strictly separated from ML probabilities, signal scores, and execution permissions.
"""
from __future__ import annotations

from app.historical_intelligence.schemas import (
    HistoricalAnalogMatch,
    HistoricalStateSnapshot,
    SampleReliability,
)


def compute_historical_confidence(
    query_state: HistoricalStateSnapshot,
    analogs: list[HistoricalAnalogMatch],
    effective_sample_size: float,
    sample_reliability: SampleReliability,
) -> float:
    """
    Computes distinct Historical Confidence score in [0.0, 1.0] (§22).
    Combines:
    1. Sample Size Adequacy (0.30)
    2. Average Similarity Quality (0.25)
    3. Outcome Directional Consensus (0.20)
    4. Regime Consistency (0.15)
    5. Data Quality Score (0.10)
    """
    if not analogs or sample_reliability == SampleReliability.INSUFFICIENT:
        return 0.10

    n = len(analogs)

    # 1. Sample Size Adequacy (Target ESS = 50)
    sample_score = min(1.0, effective_sample_size / 50.0)

    # 2. Similarity Quality
    avg_sim = sum(a.similarity_score for a in analogs) / n
    sim_score = max(0.0, min(1.0, (avg_sim - 0.50) / 0.40))  # Scales 0.50 - 0.90 to 0 - 1

    # 3. Outcome Directional Consensus (30m horizon)
    bull_count = sum(1 for a in analogs if a.outcome_30m.direction == "BULLISH")
    bear_count = sum(1 for a in analogs if a.outcome_30m.direction == "BEARISH")
    consensus_score = abs(bull_count - bear_count) / n

    # 4. Regime Consistency
    q_regime = query_state.market_regime
    regime_match_count = sum(1 for a in analogs if a.matched_regime == q_regime)
    regime_score = regime_match_count / n

    # 5. Data Quality
    dq_score = query_state.data_quality_score

    # Composite Confidence
    confidence = (
        (0.30 * sample_score)
        + (0.25 * sim_score)
        + (0.20 * consensus_score)
        + (0.15 * regime_score)
        + (0.10 * dq_score)
    )

    return round(max(0.05, min(0.99, confidence)), 4)
