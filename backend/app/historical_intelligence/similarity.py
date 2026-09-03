"""
Multi-Factor Composite Similarity Scoring Engine — §14
"""
from __future__ import annotations

import math
from typing import Tuple
from app.historical_intelligence.schemas import (
    HistoricalStateSnapshot,
    SimilarityBreakdown,
    MarketRegime,
    VolatilityRegime,
    SessionPhase,
)
from app.historical_intelligence.versioning import SIMILARITY_VERSION

# Configurable and versioned similarity weights (§14)
DEFAULT_SIMILARITY_WEIGHTS: dict[str, float] = {
    "embedding": 0.50,
    "regime": 0.15,
    "volatility": 0.10,
    "session": 0.10,
    "structure": 0.10,
    "market_context": 0.05,
}


def cosine_similarity(v1: list[float], v2: list[float]) -> float:
    """Compute cosine similarity between two numeric vectors in [-1.0, 1.0], scaled to [0.0, 1.0]."""
    if len(v1) != len(v2) or not v1:
        return 0.0

    dot = sum(a * b for a, b in zip(v1, v2))
    norm1 = math.sqrt(sum(a * a for a in v1))
    norm2 = math.sqrt(sum(b * b for b in v2))

    if norm1 < 1e-12 or norm2 < 1e-12:
        return 0.0

    raw_cos = dot / (norm1 * norm2)
    # Scale from [-1, 1] to [0, 1]
    return max(0.0, min(1.0, (raw_cos + 1.0) / 2.0))


def compute_regime_similarity(r1: MarketRegime, r2: MarketRegime) -> float:
    """Regime compatibility score."""
    if r1 == r2:
        return 1.0
    # Compatible regimes
    bull_pair = {MarketRegime.TRENDING_BULLISH, MarketRegime.BREAKOUT}
    bear_pair = {MarketRegime.TRENDING_BEARISH, MarketRegime.BREAKDOWN}
    if r1 in bull_pair and r2 in bull_pair:
        return 0.75
    if r1 in bear_pair and r2 in bear_pair:
        return 0.75
    if r1 == MarketRegime.SIDEWAYS or r2 == MarketRegime.SIDEWAYS:
        return 0.40
    # Diametrically opposed regimes
    return 0.05


def compute_volatility_similarity(v1: VolatilityRegime, v2: VolatilityRegime) -> float:
    """Volatility regime proximity score."""
    if v1 == v2:
        return 1.0
    scale = {
        VolatilityRegime.LOW_VOLATILITY: 1,
        VolatilityRegime.NORMAL_VOLATILITY: 2,
        VolatilityRegime.HIGH_VOLATILITY: 3,
        VolatilityRegime.EXTREME_VOLATILITY: 4,
    }
    step_diff = abs(scale.get(v1, 2) - scale.get(v2, 2))
    if step_diff == 1:
        return 0.70
    elif step_diff == 2:
        return 0.35
    else:
        return 0.10


def compute_session_similarity(s1: SessionPhase, s2: SessionPhase) -> float:
    """Session phase temporal proximity score."""
    if s1 == s2:
        return 1.0
    # Sessions with similar liquidity/order flow dynamics
    order = [
        SessionPhase.PRE_MARKET,
        SessionPhase.MARKET_OPEN,
        SessionPhase.EARLY_SESSION,
        SessionPhase.MID_SESSION,
        SessionPhase.AFTERNOON,
        SessionPhase.CLOSING_PHASE,
        SessionPhase.POST_MARKET,
    ]
    try:
        idx1 = order.index(s1)
        idx2 = order.index(s2)
        diff = abs(idx1 - idx2)
        if diff == 1:
            return 0.75
        elif diff == 2:
            return 0.45
        else:
            return 0.15
    except ValueError:
        return 0.50  # Perpetual / fallback


def compute_structure_similarity(s1: HistoricalStateSnapshot, s2: HistoricalStateSnapshot) -> float:
    """Market structure similarity: swings, compression, breakout distance."""
    struct1 = s1.feature_vector.structure
    struct2 = s2.feature_vector.structure

    matches = 0
    if struct1.is_hh == struct2.is_hh:
        matches += 1
    if struct1.is_hl == struct2.is_hl:
        matches += 1
    if struct1.is_lh == struct2.is_lh:
        matches += 1
    if struct1.is_ll == struct2.is_ll:
        matches += 1
    if struct1.consolidation == struct2.consolidation:
        matches += 1
    if struct1.retest_state == struct2.retest_state:
        matches += 2

    # Breakout distance proximity
    atr = max(1.0, s1.feature_vector.volume_vol.atr)
    dist_diff = abs(struct1.breakout_distance - struct2.breakout_distance) / atr
    dist_sim = max(0.0, 1.0 - (dist_diff / 3.0))

    return round((matches / 7.0) * 0.7 + (dist_sim * 0.3), 4)


def compute_market_context_similarity(s1: HistoricalStateSnapshot, s2: HistoricalStateSnapshot) -> float:
    """Market context similarity: breadth, PCR, futures basis."""
    pcr1 = s1.feature_vector.options.pcr_oi
    pcr2 = s2.feature_vector.options.pcr_oi
    pcr_sim = max(0.0, 1.0 - abs(pcr1 - pcr2) / 1.0)

    fut1 = s1.feature_vector.futures.buildup
    fut2 = s2.feature_vector.futures.buildup
    fut_sim = 1.0 if fut1 == fut2 else 0.40

    return round((pcr_sim * 0.5) + (fut_sim * 0.5), 4)


def compute_composite_similarity(
    query_state: HistoricalStateSnapshot,
    candidate_state: HistoricalStateSnapshot,
    weights: dict[str, float] | None = None,
) -> Tuple[float, SimilarityBreakdown]:
    """
    Computes final composite similarity score according to §14:
    final = 0.50*embedding + 0.15*regime + 0.10*volatility + 0.10*session + 0.10*structure + 0.05*context
    """
    w = weights or DEFAULT_SIMILARITY_WEIGHTS

    # 1. Embedding Similarity (from unit-norm vectors)
    emb_sim = cosine_similarity(query_state.embedding, candidate_state.embedding)

    # 2. Regime Similarity
    reg_sim = compute_regime_similarity(query_state.market_regime, candidate_state.market_regime)

    # 3. Volatility Similarity
    vol_sim = compute_volatility_similarity(query_state.volatility_regime, candidate_state.volatility_regime)

    # 4. Session Similarity
    sess_sim = compute_session_similarity(query_state.session, candidate_state.session)

    # 5. Structure Similarity
    struct_sim = compute_structure_similarity(query_state, candidate_state)

    # 6. Market Context Similarity
    ctx_sim = compute_market_context_similarity(query_state, candidate_state)

    final_score = (
        (w["embedding"] * emb_sim)
        + (w["regime"] * reg_sim)
        + (w["volatility"] * vol_sim)
        + (w["session"] * sess_sim)
        + (w["structure"] * struct_sim)
        + (w["market_context"] * ctx_sim)
    )

    breakdown = SimilarityBreakdown(
        embedding_similarity=round(emb_sim, 4),
        regime_similarity=round(reg_sim, 4),
        volatility_similarity=round(vol_sim, 4),
        session_similarity=round(sess_sim, 4),
        structure_similarity=round(struct_sim, 4),
        market_context_similarity=round(ctx_sim, 4),
        final_similarity=round(final_score, 4),
    )

    return round(final_score, 4), breakdown
