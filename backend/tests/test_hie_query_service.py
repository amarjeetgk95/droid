"""
Tests for Central HIE Query Service & Output Contract (§§1, 24, 25, 26, 40)
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.historical_intelligence.schemas import (
    CandleData,
    HistoricalIntelligenceResult,
    HIEStatus,
    SampleReliability,
)
from app.historical_intelligence.state_builder import state_builder
from app.historical_intelligence.retriever import InMemoryVectorStore, QdrantRetriever
from app.historical_intelligence.outcome_engine import construct_forward_outcomes
from app.historical_intelligence.query_service import HistoricalIntelligenceService
from app.historical_intelligence.cache import HIECache
from app.historical_intelligence.ai_context import ai_context_generator


def _candles(count: int, base_p: float, end_time: datetime, trend: float = 2.0) -> list[CandleData]:
    end_ms = int(end_time.timestamp() * 1000)
    return [
        CandleData(
            timestamp_utc=end_ms - (count - i) * 60000,
            open=base_p + i * trend,
            high=base_p + i * trend + 4,
            low=base_p + i * trend - 2,
            close=base_p + i * trend + 1,
            volume=1200.0,
        )
        for i in range(count)
    ]


class TestHIEQueryService:

    @pytest.fixture
    def setup_service(self):
        store = InMemoryVectorStore()
        cache = HIECache(default_ttl_seconds=60)
        retriever = QdrantRetriever()
        retriever.in_memory_index = store

        base_t = datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc)
        for i in range(30):
            t = base_t + timedelta(hours=i)
            c = _candles(25, 24000.0 + i * 20, t, trend=3.0)
            fut_c = _candles(60, c[-1].close, t + timedelta(minutes=60), trend=1.5)

            snap = state_builder.build_snapshot("NIFTY", c, t, "1m", vix=14.0)
            out = construct_forward_outcomes(snap.snapshot_id, "NIFTY", t, c[-1].close, fut_c)
            store.upsert(snap, out)

        service = HistoricalIntelligenceService(retriever=retriever, cache=cache)
        return service, store, cache

    @pytest.mark.asyncio
    async def test_mode_a_market_state_query_and_contract(self, setup_service):
        service, store, _ = setup_service
        now = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
        current_candles = _candles(25, 24500.0, now, trend=3.0)

        result = await service.analyze_state(
            instrument="NIFTY",
            candles=current_candles,
            timestamp=now,
            timeframe="1m",
            top_k=20,
            min_similarity=0.40,
            mode="MARKET_STATE",
        )

        assert isinstance(result, HistoricalIntelligenceResult)
        assert result.instrument == "NIFTY"
        assert result.sample_count > 0
        assert result.effective_sample_size > 0
        assert 0.0 <= result.similarity_score <= 1.0
        assert 0.0 <= result.probability_15m <= 1.0
        assert 0.0 <= result.probability_30m <= 1.0
        assert 0.0 <= result.probability_60m <= 1.0
        assert 0.0 <= result.bullish_probability <= 1.0
        assert 0.0 <= result.confidence <= 1.0
        assert result.status in (HIEStatus.READY, HIEStatus.INSUFFICIENT_SAMPLE)
        assert result.feature_version == "1.0.0"
        assert result.embedding_version == "1.0.0"

    @pytest.mark.asyncio
    async def test_mode_b_candidate_triggered_analysis(self, setup_service):
        service, store, _ = setup_service
        now = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
        current_candles = _candles(25, 24600.0, now, trend=4.0)

        result = await service.analyze_state(
            instrument="NIFTY",
            candles=current_candles,
            timestamp=now,
            timeframe="1m",
            top_k=15,
            min_similarity=0.40,
            mode="CANDIDATE",
            candidate_meta={"strategy_id": "ORB_BREAKOUT_BULLISH"},
        )

        assert result.sample_count > 0
        assert len(result.analog_matches) <= 15
        # Top analog matches have valid forward outcomes
        top_match = result.analog_matches[0]
        assert top_match.outcome_15m.horizon_minutes == 15
        assert top_match.outcome_30m.horizon_minutes == 30
        assert top_match.outcome_60m.horizon_minutes == 60

    @pytest.mark.asyncio
    async def test_hot_caching_behavior(self, setup_service):
        service, store, cache = setup_service
        now = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
        current_candles = _candles(25, 24500.0, now, trend=3.0)

        # Initial call - cache miss
        r1 = await service.analyze_state("NIFTY", current_candles, timestamp=now)
        # Second call in same minute - cache hit
        r2 = await service.analyze_state("NIFTY", current_candles, timestamp=now)

        assert r1.historical_analysis_id == r2.historical_analysis_id

    @pytest.mark.asyncio
    async def test_safe_failure_on_no_match(self):
        # Empty corpus
        empty_store = InMemoryVectorStore()
        retriever = QdrantRetriever()
        retriever.in_memory_index = empty_store
        service = HistoricalIntelligenceService(retriever=retriever, cache=HIECache())

        now = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
        current_candles = _candles(25, 24500.0, now)

        result = await service.analyze_state("NIFTY", current_candles, timestamp=now)
        assert result.status == HIEStatus.NO_MATCH
        assert result.sample_count == 0
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_ai_context_generator_payload(self, setup_service):
        service, store, _ = setup_service
        now = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
        current_candles = _candles(25, 24500.0, now, trend=3.0)

        result = await service.analyze_state("NIFTY", current_candles, timestamp=now, top_k=20, min_similarity=0.40)
        ai_ctx = ai_context_generator.generate_context(result)

        assert ai_ctx.total_analogs == result.sample_count
        assert "Historical Intelligence Analysis" in ai_ctx.historical_summary_text
        assert "15m Horizon" in ai_ctx.historical_summary_text
        assert "30m Horizon" in ai_ctx.historical_summary_text
        assert "60m Horizon" in ai_ctx.historical_summary_text
        assert "failure_rate" in ai_ctx.failure_analysis
