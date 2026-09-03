"""
Historical AI Orchestrator — "What Happened Last Time?" Engine
Provides empirical evidence from similar historical market setups to Main AI.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, Sequence
import structlog

from app.historical_intelligence.schemas import (
    CandleData,
    HistoricalStateSnapshot,
    HistoricalOutcomeRecord,
    HistoricalAIResult,
    HorizonProbabilities,
)
from app.historical_intelligence.state_builder import state_builder
from app.historical_intelligence.similarity_engine import similarity_engine, SimilarityEngine
from app.historical_intelligence.outcome_engine import outcome_engine, OutcomeEngine
from app.historical_intelligence.retriever import vector_retriever

logger = structlog.get_logger()


class HistoricalAI:
    """
    Historical AI Module.
    When a meaningful trading setup is detected, searches the historical database
    for point-in-time safe similar market states, calculates actual forward outcomes,
    and returns empirical 15m / 30m / 60m probabilities to Main AI.
    """

    def __init__(
        self,
        retriever=vector_retriever,
        sim_engine: Optional[SimilarityEngine] = None,
        out_engine: Optional[OutcomeEngine] = None,
    ):
        self.retriever = retriever
        self.similarity_engine = sim_engine or similarity_engine
        self.outcome_engine = out_engine or outcome_engine

    def register_snapshot_and_outcome(
        self,
        snapshot: HistoricalStateSnapshot,
        outcome: Optional[HistoricalOutcomeRecord] = None,
    ) -> None:
        """
        Store a historical state snapshot and its actual forward outcome into the historical store.
        Maintains the historical truth repository for similarity searches.
        """
        self.retriever.in_memory_index.upsert(snapshot, outcome)

    def count_historical_records(self) -> int:
        """Return total number of historical snapshots currently stored."""
        return self.retriever.in_memory_index.count()

    def clear_store(self) -> None:
        """Clear all historical state snapshots and outcomes (useful in test setups)."""
        self.retriever.in_memory_index.clear()

    async def analyze_setup(
        self,
        instrument: str,
        candles: list[CandleData],
        timestamp: Optional[datetime] = None,
        timeframe: str = "1m",
        prior_bias: str = "BULLISH",
        indicators: Optional[Any] = None,
        key_levels: Optional[Any] = None,
        options_analytics: Optional[Any] = None,
        futures_data: Optional[Any] = None,
        vix: float = 14.0,
        min_samples: int = 10,
        top_k: int = 50,
        min_similarity: float = 0.60,
        temporal_cutoff: Optional[datetime] = None,
        is_crypto: bool = False,
    ) -> HistoricalAIResult:
        """
        Main entrypoint: analyzes a detected trading setup against historical data.
        Runs asynchronously and point-in-time safely.
        """
        now_utc = timestamp or datetime.now(timezone.utc)
        cutoff = temporal_cutoff or now_utc

        # 1. Missing or empty historical database check -> UNKNOWN
        total_history = self.count_historical_records()
        if total_history == 0:
            logger.info("historical_ai_missing_data", instrument=instrument, reason="store_empty")
            return HistoricalAIResult(
                status="UNKNOWN",
                sample_count=0,
                probability_15m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_30m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_60m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                failure_rate=0.0,
                confidence="UNKNOWN",
                historical_context="Historical market database is unpopulated or missing. Cannot evaluate historical analogues.",
            )

        # 2. Check if candles are provided
        if not candles:
            return HistoricalAIResult(
                status="UNKNOWN",
                sample_count=0,
                probability_15m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_30m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_60m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                failure_rate=0.0,
                confidence="UNKNOWN",
                historical_context="No current market candles provided to build setup state.",
            )

        # 3. Build Point-In-Time Query State using existing Feature Engine
        try:
            query_snapshot = state_builder.build_snapshot(
                instrument=instrument,
                candles=candles,
                timestamp=now_utc,
                timeframe=timeframe,
                indicators=indicators,
                key_levels=key_levels,
                options_analytics=options_analytics,
                futures_data=futures_data,
                vix=vix,
                is_crypto=is_crypto,
            )
        except Exception as e:
            logger.warning("historical_ai_state_builder_error", instrument=instrument, error=str(e))
            return HistoricalAIResult(
                status="UNKNOWN",
                sample_count=0,
                probability_15m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_30m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_60m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                failure_rate=0.0,
                confidence="UNKNOWN",
                historical_context=f"Failed to build current market state from features: {str(e)}",
            )

        # 4. Search Similar Historical Setups (PIT safe: strictly cand.timestamp < cutoff)
        matches = self.similarity_engine.find_similar_states(
            query_state=query_snapshot,
            top_k=top_k,
            min_similarity=min_similarity,
            temporal_cutoff=cutoff,
        )
        sample_count = len(matches)

        # 5. Insufficient Sample Check (< min_samples) -> INSUFFICIENT_SAMPLE
        if sample_count < min_samples:
            return HistoricalAIResult(
                status="INSUFFICIENT_SAMPLE",
                sample_count=sample_count,
                probability_15m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_30m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                probability_60m=HorizonProbabilities(bullish=0.0, bearish=0.0, neutral=0.0),
                failure_rate=0.0,
                confidence="LOW",
                historical_context=f"Insufficient similar historical setups found (N={sample_count} < {min_samples}). Empirical edge cannot be reliably inferred.",
            )

        # 6. Calculate Actual Forward Outcomes & Empirical Probabilities
        agg = self.outcome_engine.aggregate_matched_outcomes(matches, prior_bias=prior_bias)

        prob_15 = HorizonProbabilities(**agg["probability_15m"])
        prob_30 = HorizonProbabilities(**agg["probability_30m"])
        prob_60 = HorizonProbabilities(**agg["probability_60m"])
        failure_rate = float(agg["failure_rate"])

        # 7. Determine Confidence based on sample count and empirical consistency
        if sample_count >= 50:
            confidence = "HIGH" if (prob_15.bullish >= 0.55 or prob_15.bearish >= 0.55) else "MEDIUM"
        elif sample_count >= 20:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        # 8. Synthesize Grounded Historical Narrative
        narrative = self._generate_context_summary(
            instrument=instrument,
            sample_count=sample_count,
            prob_15=prob_15,
            prob_30=prob_30,
            prob_60=prob_60,
            failure_rate=failure_rate,
            prior_bias=prior_bias,
        )

        return HistoricalAIResult(
            status="READY",
            sample_count=sample_count,
            probability_15m=prob_15,
            probability_30m=prob_30,
            probability_60m=prob_60,
            failure_rate=failure_rate,
            confidence=confidence,
            historical_context=narrative,
            median_return_15m=agg.get("median_return_15m"),
            median_return_30m=agg.get("median_return_30m"),
            median_return_60m=agg.get("median_return_60m"),
            median_mfe=agg.get("median_mfe"),
            median_mae=agg.get("median_mae"),
            continuation_rate=agg.get("continuation_rate"),
            reversal_rate=agg.get("reversal_rate"),
        )

    def _generate_context_summary(
        self,
        instrument: str,
        sample_count: int,
        prob_15: HorizonProbabilities,
        prob_30: HorizonProbabilities,
        prob_60: HorizonProbabilities,
        failure_rate: float,
        prior_bias: str,
    ) -> str:
        """Generate concise, factual summary text without hallucinating probabilities."""
        bias_lower = prior_bias.lower()
        # Check directional bias
        primary_prob_15 = prob_15.bullish if prior_bias == "BULLISH" else prob_15.bearish
        primary_prob_60 = prob_60.bullish if prior_bias == "BULLISH" else prob_60.bearish

        if primary_prob_15 >= 0.55:
            if primary_prob_60 < primary_prob_15 - 0.08:
                trajectory = "but the edge weakened over the 60-minute horizon."
            elif primary_prob_60 > primary_prob_15 + 0.05:
                trajectory = "and the directional edge strengthened over the 60-minute horizon."
            else:
                trajectory = "with steady persistence across the 60-minute horizon."
            return (
                f"Similar historical setups generally favored {bias_lower} continuation, {trajectory}"
            )
        elif prob_15.neutral >= 0.45:
            return (
                f"Similar historical setups showed high chop/neutral consolidation ({int(prob_15.neutral * 100)}% neutral at 15m), with failure rate of {int(failure_rate * 100)}%."
            )
        else:
            opp_bias = "bearish" if prior_bias == "BULLISH" else "bullish"
            opp_prob = prob_15.bearish if prior_bias == "BULLISH" else prob_15.bullish
            return (
                f"Similar historical setups exhibited mixed outcomes ({int(primary_prob_15 * 100)}% {bias_lower} vs {int(opp_prob * 100)}% {opp_bias}), with failure rate of {int(failure_rate * 100)}%."
            )


historical_ai = HistoricalAI()
