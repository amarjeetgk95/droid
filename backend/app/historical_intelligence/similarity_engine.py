"""
Similarity Engine — Simple Historical AI
Compares the current market state with historical states and returns the most similar ones point-in-time safely.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Sequence
import structlog

from app.historical_intelligence.schemas import (
    HistoricalStateSnapshot,
    HistoricalAnalogMatch,
    HistoricalOutcomeRecord,
    ForwardOutcomeHorizon,
)
from app.historical_intelligence.similarity import compute_composite_similarity
from app.historical_intelligence.recency import compute_recency_weight, is_in_fresh_window
from app.historical_intelligence.retriever import vector_retriever

logger = structlog.get_logger()


class SimilarityEngine:
    """
    Empirical Similarity Engine for Historical Setups.
    Compares the current market state against historical snapshots with strict PIT safety (T_hist < T_query).
    """

    def __init__(self, retriever=vector_retriever):
        self.retriever = retriever

    def compute_similarity(
        self,
        state_a: HistoricalStateSnapshot,
        state_b: HistoricalStateSnapshot,
    ) -> float:
        """Calculate composite similarity between two historical states [0.0 to 1.0]."""
        score, _ = compute_composite_similarity(state_a, state_b)
        return score

    def find_similar_states(
        self,
        query_state: HistoricalStateSnapshot,
        historical_snapshots: Optional[Sequence[HistoricalStateSnapshot]] = None,
        top_k: int = 50,
        min_similarity: float = 0.60,
        temporal_cutoff: Optional[datetime] = None,
        fresh_window_days: int = 10,
    ) -> list[HistoricalAnalogMatch]:
        """
        Find top-k historical market states most similar to query_state.
        Strict Point-In-Time (PIT) Rule:
          Only candidates strictly BEFORE temporal_cutoff (or query_state.timestamp) are evaluated.
        """
        cutoff = temporal_cutoff or query_state.timestamp

        # If candidates are explicitly provided, evaluate those; otherwise fetch from retriever's store
        if historical_snapshots is not None:
            candidates = historical_snapshots
            get_outcome_fn = lambda snap_id: self.retriever.in_memory_index.get_outcome(snap_id)
        else:
            candidates = list(self.retriever.in_memory_index._snapshots.values())
            get_outcome_fn = lambda snap_id: self.retriever.in_memory_index.get_outcome(snap_id)

        matches: list[HistoricalAnalogMatch] = []

        for cand in candidates:
            # 1. Point-in-time safety check: T_hist must be strictly < cutoff
            if cand.timestamp >= cutoff:
                continue

            # 2. Exclude same snapshot ID
            if cand.snapshot_id == query_state.snapshot_id:
                continue

            # 3. Only match same or compatible instrument
            if cand.instrument != query_state.instrument:
                continue

            # 4. Compute composite similarity
            sim_score, breakdown = compute_composite_similarity(query_state, cand)
            if sim_score < min_similarity:
                continue

            # 5. Fetch associated forward outcomes
            outcome_rec: Optional[HistoricalOutcomeRecord] = get_outcome_fn(cand.snapshot_id)
            if outcome_rec is not None:
                out_15 = outcome_rec.outcome_15m
                out_30 = outcome_rec.outcome_30m
                out_60 = outcome_rec.outcome_60m
            else:
                out_15 = ForwardOutcomeHorizon(horizon_minutes=15, return_pct=0.0, direction="NEUTRAL", mfe_pct=0.0, mae_pct=0.0, high_price=0.0, low_price=0.0, target_hit=False, stop_hit=False)
                out_30 = ForwardOutcomeHorizon(horizon_minutes=30, return_pct=0.0, direction="NEUTRAL", mfe_pct=0.0, mae_pct=0.0, high_price=0.0, low_price=0.0, target_hit=False, stop_hit=False)
                out_60 = ForwardOutcomeHorizon(horizon_minutes=60, return_pct=0.0, direction="NEUTRAL", mfe_pct=0.0, mae_pct=0.0, high_price=0.0, low_price=0.0, target_hit=False, stop_hit=False)

            # 6. Recency weight
            temporal_w = compute_recency_weight(query_state.timestamp, cand.timestamp)
            fresh = is_in_fresh_window(query_state.timestamp, cand.timestamp, fresh_window_days)

            matches.append(
                HistoricalAnalogMatch(
                    snapshot_id=cand.snapshot_id,
                    instrument=cand.instrument,
                    timeframe=cand.timeframe,
                    timestamp=cand.timestamp,
                    similarity_score=sim_score,
                    breakdown=breakdown,
                    matched_regime=cand.market_regime,
                    session_phase=cand.session,
                    outcome_15m=out_15,
                    outcome_30m=out_30,
                    outcome_60m=out_60,
                    temporal_weight=temporal_w,
                    is_fresh_window=fresh,
                )
            )

        # Sort descending by composite similarity score
        matches.sort(key=lambda m: (m.similarity_score * m.temporal_weight), reverse=True)
        return matches[:top_k]


similarity_engine = SimilarityEngine()
