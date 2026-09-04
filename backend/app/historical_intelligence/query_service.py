"""
Central Historical Intelligence Query Service — §§1, 24, 25, 29, 41
Coordinates State Building, Qdrant Retrieval, Multi-Horizon Statistics, and Caching.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
import structlog

from app.historical_intelligence.schemas import (
    CandleData,
    HistoricalStateSnapshot,
    HistoricalQuery,
    HistoricalIntelligenceResult,
    HIEStatus,
    SampleReliability,
)
from app.historical_intelligence.state_builder import state_builder
from app.historical_intelligence.retriever import vector_retriever
from app.historical_intelligence.statistics import (
    compute_horizon_statistics,
    calculate_effective_sample_size,
    classify_sample_reliability,
)
from app.historical_intelligence.confidence import compute_historical_confidence
from app.historical_intelligence.cache import hie_cache
from app.historical_intelligence.monitoring import hie_monitor
from app.historical_intelligence.versioning import FEATURE_VERSION, EMBEDDING_VERSION

logger = structlog.get_logger()


class HistoricalIntelligenceService:
    """
    Production Historical Intelligence Service (HIE) (§§1, 24, 25, 29).
    """

    def __init__(self, retriever=vector_retriever, cache=hie_cache):
        self.retriever = retriever
        self.cache = cache

    async def analyze_state(
        self,
        instrument: str,
        candles: list[CandleData],
        timestamp: Optional[datetime] = None,
        timeframe: str = "1m",
        indicators: Optional[Any] = None,
        key_levels: Optional[Any] = None,
        options_analytics: Optional[Any] = None,
        futures_data: Optional[Any] = None,
        vix: float = 14.0,
        top_k: int = 50,
        min_similarity: float = 0.65,
        mode: str = "MARKET_STATE",
        candidate_meta: Optional[dict[str, Any]] = None,
        regime_filter: Optional[Any] = None,
        session_filter: Optional[Any] = None,
        volatility_filter: Optional[Any] = None,
        is_crypto: bool = False,
    ) -> HistoricalIntelligenceResult:
        """
        Main query entrypoint for Mode A (Market State) and Mode B (Candidate Analysis).
        """
        start_time = time.perf_counter()
        now_utc = timestamp or datetime.now(timezone.utc)
        minute_epoch = int(now_utc.timestamp()) // 60

        # 1. State Building (§4)
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
            logger.error("hie_state_builder_error", instrument=instrument, error=str(e))
            return self._build_failure_result(
                instrument=instrument,
                timestamp=now_utc,
                status=HIEStatus.UNAVAILABLE,
            )

        # 2. Check Hot Cache (§30)
        cached = self.cache.get(
            instrument=instrument,
            timeframe=timeframe,
            regime=query_snapshot.market_regime.value,
            session=query_snapshot.session.value,
            minute_epoch=minute_epoch,
        )
        if cached is not None:
            return cached

        # 3. Vector ANN Retrieval (§12, §13)
        t_retrieval_start = time.perf_counter()
        query_params = HistoricalQuery(
            instrument=instrument,
            timeframe=timeframe,
            top_k=top_k,
            min_similarity=min_similarity,
            temporal_cutoff=now_utc,  # Strict lookahead prevention
            regime_filter=regime_filter,
            session_filter=session_filter,
            volatility_filter=volatility_filter,
            mode="CANDIDATE" if mode == "CANDIDATE" else "MARKET_STATE",
        )

        matches = await self.retriever.search_analogs(query_snapshot, query_params)
        ann_ms = (time.perf_counter() - t_retrieval_start) * 1000.0

        sample_count = len(matches)

        # 4. Handle Empty or Insufficient Matches (§40)
        if sample_count == 0:
            hie_monitor.record_query_latency(ann_ms, 0.0, 0.0)
            res = self._build_failure_result(
                instrument=instrument,
                timestamp=now_utc,
                query_snapshot_id=query_snapshot.snapshot_id,
                status=HIEStatus.NO_MATCH,
            )
            try:
                import asyncio
                from app.historical_intelligence.hie_persistence import persist_hie_query_audit
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(
                        persist_hie_query_audit(
                            instrument=instrument.upper(),
                            timeframe=timeframe,
                            query_mode=mode,
                            sample_count=0,
                            effective_sample_size=0.0,
                            bullish_prob=0.33,
                            confidence=0.0,
                            latency_ms=(time.perf_counter() - start_time) * 1000.0,
                        )
                    )
            except Exception:
                pass
            return res

        # 5. Outcome Retrieval & Aggregation (§15, §16, §20)
        t_agg_start = time.perf_counter()
        weights = [m.similarity_score * m.temporal_weight for m in matches]
        ess = calculate_effective_sample_size(weights)
        reliability = classify_sample_reliability(sample_count)

        stat_15 = compute_horizon_statistics(matches, 15)
        stat_30 = compute_horizon_statistics(matches, 30)
        stat_60 = compute_horizon_statistics(matches, 60)

        # Composite Confidence (§22)
        confidence = compute_historical_confidence(query_snapshot, matches, ess, reliability)
        agg_ms = (time.perf_counter() - t_agg_start) * 1000.0

        # Benchmark latencies (§41)
        hie_monitor.record_query_latency(ann_ms, 0.0, agg_ms)

        # Determine status
        status = HIEStatus.READY
        if reliability == SampleReliability.INSUFFICIENT:
            status = HIEStatus.INSUFFICIENT_SAMPLE

        # 6. Construct Canonical Output Contract (§25)
        avg_sim = sum(m.similarity_score for m in matches) / sample_count
        regime_distribution = {}
        for m in matches:
            regime_distribution[m.matched_regime.value] = regime_distribution.get(m.matched_regime.value, 0) + 1

        result = HistoricalIntelligenceResult(
            historical_analysis_id=f"hie_{uuid.uuid4().hex[:12]}",
            instrument=instrument.upper(),
            timestamp=now_utc,
            query_snapshot_id=query_snapshot.snapshot_id,
            feature_version=FEATURE_VERSION,
            embedding_version=EMBEDDING_VERSION,
            sample_count=sample_count,
            effective_sample_size=ess,
            similarity_score=round(avg_sim, 4),
            probability_15m=stat_15.bullish_probability,
            probability_30m=stat_30.bullish_probability,
            probability_60m=stat_60.bullish_probability,
            bullish_probability=stat_30.bullish_probability,
            bearish_probability=stat_30.bearish_probability,
            neutral_probability=stat_30.neutral_probability,
            continuation_probability=stat_30.continuation_probability,
            failure_probability=stat_30.failure_probability,
            reversal_probability=stat_30.reversal_probability,
            median_return_15m=stat_15.median_return,
            median_return_30m=stat_30.median_return,
            median_return_60m=stat_60.median_return,
            median_MFE=stat_30.median_mfe,
            median_MAE=stat_30.median_mae,
            target_hit_rate=stat_30.target_hit_rate,
            stop_hit_rate=stat_30.stop_hit_rate,
            historical_regime=query_snapshot.market_regime.value,
            sample_distribution=regime_distribution,
            confidence=confidence,
            data_quality=query_snapshot.data_quality_score,
            computed_at=now_utc,
            published_at=datetime.now(timezone.utc),
            staleness_seconds=round(time.perf_counter() - start_time, 4),
            status=status,
            analog_matches=matches[:10],
        )

        # 7. Write into hot cache
        self.cache.set(
            instrument=instrument,
            timeframe=timeframe,
            regime=query_snapshot.market_regime.value,
            session=query_snapshot.session.value,
            minute_epoch=minute_epoch,
            result=result,
        )

        # 8. Persist snapshot & query audit to Supabase (§3.1, §36)
        try:
            import asyncio
            from app.historical_intelligence.hie_persistence import persist_hie_snapshot, persist_hie_query_audit
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(persist_hie_snapshot(query_snapshot))
                loop.create_task(
                    persist_hie_query_audit(
                        instrument=instrument.upper(),
                        timeframe=timeframe,
                        query_mode=mode,
                        sample_count=sample_count,
                        effective_sample_size=ess,
                        bullish_prob=float(stat_30.bullish_probability),
                        confidence=confidence,
                        latency_ms=(time.perf_counter() - start_time) * 1000.0,
                    )
                )
        except Exception as pe:
            logger.debug("hie_async_persist_failed", error=str(pe))

        return result

    def _build_failure_result(
        self,
        instrument: str,
        timestamp: datetime,
        query_snapshot_id: str = "none",
        status: HIEStatus = HIEStatus.UNKNOWN,
    ) -> HistoricalIntelligenceResult:
        """Explicit UNKNOWN / Safe failure construction (§40)."""
        return HistoricalIntelligenceResult(
            historical_analysis_id=f"hie_{uuid.uuid4().hex[:12]}",
            instrument=instrument.upper(),
            timestamp=timestamp,
            query_snapshot_id=query_snapshot_id,
            feature_version=FEATURE_VERSION,
            embedding_version=EMBEDDING_VERSION,
            sample_count=0,
            effective_sample_size=0.0,
            similarity_score=0.0,
            probability_15m=0.33,
            probability_30m=0.33,
            probability_60m=0.33,
            bullish_probability=0.33,
            bearish_probability=0.33,
            neutral_probability=0.34,
            continuation_probability=0.0,
            failure_probability=0.0,
            reversal_probability=0.0,
            median_return_15m=0.0,
            median_return_30m=0.0,
            median_return_60m=0.0,
            median_MFE=0.0,
            median_MAE=0.0,
            target_hit_rate=0.0,
            stop_hit_rate=0.0,
            historical_regime="UNKNOWN",
            sample_distribution={},
            confidence=0.0,
            data_quality=0.0,
            computed_at=timestamp,
            published_at=datetime.now(timezone.utc),
            staleness_seconds=0.0,
            status=status,
            analog_matches=[],
        )


hie_service = HistoricalIntelligenceService()
