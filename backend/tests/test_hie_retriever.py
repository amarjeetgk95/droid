"""
Tests for Vector Retriever, ANN Search, and Hierarchical Filtering — §§8, 9, 12, 13, 14, 18, 19
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.historical_intelligence.schemas import (
    CandleData,
    HistoricalQuery,
    MarketRegime,
    VolatilityRegime,
    SessionPhase,
)
from app.historical_intelligence.state_builder import state_builder
from app.historical_intelligence.retriever import InMemoryVectorStore, QdrantRetriever
from app.historical_intelligence.outcome_engine import construct_forward_outcomes
from app.historical_intelligence.similarity import compute_composite_similarity, cosine_similarity
from app.historical_intelligence.recency import compute_recency_weight, is_in_fresh_window


def _make_candles(count: int, base_price: float, trend_step: float, end_time: datetime) -> list[CandleData]:
    end_ms = int(end_time.timestamp() * 1000)
    candles = []
    for i in range(count):
        ts = end_ms - (count - i) * 60000
        p = base_price + i * trend_step
        candles.append(CandleData(
            timestamp_utc=ts,
            open=p,
            high=p + 5.0,
            low=p - 3.0,
            close=p + 2.0,
            volume=1500.0,
        ))
    return candles


class TestHIERetriever:

    @pytest.fixture
    def setup_corpus(self):
        store = InMemoryVectorStore()
        base_time = datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc)

        snapshots = []
        for i in range(20):
            t = base_time + timedelta(hours=i)
            trend = 5.0 if i % 2 == 0 else -5.0
            candles = _make_candles(25, 24000.0, trend, t)
            fut_candles = _make_candles(60, candles[-1].close, trend * 0.5, t + timedelta(minutes=60))

            snap = state_builder.build_snapshot(
                instrument="NIFTY",
                candles=candles,
                timestamp=t,
                timeframe="1m",
                vix=13.0 + (i % 8),
            )
            out = construct_forward_outcomes(
                snapshot_id=snap.snapshot_id,
                instrument="NIFTY",
                timestamp=t,
                entry_price=candles[-1].close,
                future_candles=fut_candles,
            )
            store.upsert(snap, out)
            snapshots.append(snap)

        return store, snapshots

    def test_vector_store_upsert_and_count(self, setup_corpus):
        store, snapshots = setup_corpus
        assert store.count() == 20
        # Retrieve outcome for first
        out = store.get_outcome(snapshots[0].snapshot_id)
        assert out is not None
        assert out.outcome_15m.horizon_minutes == 15
        assert out.outcome_30m.horizon_minutes == 30
        assert out.outcome_60m.horizon_minutes == 60

    def test_hierarchical_search_filtering(self, setup_corpus):
        store, snapshots = setup_corpus

        # Query state at later timestamp
        query_time = datetime(2026, 3, 3, 6, 0, tzinfo=timezone.utc)
        query_candles = _make_candles(25, 24100.0, 5.0, query_time)
        query_snap = state_builder.build_snapshot("NIFTY", query_candles, query_time, "1m")

        # 1. Search without regime filter
        q_all = HistoricalQuery(instrument="NIFTY", timeframe="1m", top_k=20, min_similarity=0.50)
        matches_all = store.search(query_snap, q_all)
        assert len(matches_all) > 0

        # 2. Search with strict regime filter
        target_regime = query_snap.market_regime
        q_regime = HistoricalQuery(
            instrument="NIFTY",
            timeframe="1m",
            top_k=20,
            min_similarity=0.50,
            regime_filter=target_regime,
        )
        matches_regime = store.search(query_snap, q_regime)
        assert all(m.matched_regime == target_regime for m in matches_regime)

    def test_composite_similarity_breakdown(self, setup_corpus):
        _, snapshots = setup_corpus
        s1 = snapshots[0]
        s2 = snapshots[1]

        score, breakdown = compute_composite_similarity(s1, s2)
        assert 0.0 <= score <= 1.0
        assert 0.0 <= breakdown.embedding_similarity <= 1.0
        assert 0.0 <= breakdown.regime_similarity <= 1.0
        assert 0.0 <= breakdown.volatility_similarity <= 1.0
        assert 0.0 <= breakdown.session_similarity <= 1.0
        assert 0.0 <= breakdown.structure_similarity <= 1.0
        assert 0.0 <= breakdown.market_context_similarity <= 1.0
        assert breakdown.final_similarity == score

    def test_recency_and_fresh_window(self):
        t_now = datetime(2026, 3, 4, 10, 0, tzinfo=timezone.utc)
        t_recent = t_now - timedelta(days=3)
        t_old = t_now - timedelta(days=150)

        w_recent = compute_recency_weight(t_now, t_recent)
        w_old = compute_recency_weight(t_now, t_old)

        # Recent states have higher temporal weight than old states
        assert w_recent > w_old
        # But old states preserve non-zero floor (>= 0.50)
        assert w_old >= 0.50

        # Fresh window check (10-day window)
        assert is_in_fresh_window(t_now, t_recent, fresh_window_days=10) is True
        assert is_in_fresh_window(t_now, t_old, fresh_window_days=10) is False
