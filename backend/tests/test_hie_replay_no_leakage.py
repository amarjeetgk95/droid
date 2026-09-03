"""
Tests for Deterministic Replay & Strict Lookahead Leakage Prevention — §§31, 32
"""
import pytest
from datetime import datetime, timezone, timedelta
from app.historical_intelligence.schemas import CandleData
from app.historical_intelligence.state_builder import state_builder
from app.historical_intelligence.outcome_engine import construct_forward_outcomes
from app.historical_intelligence.retriever import InMemoryVectorStore
from app.historical_intelligence.replay import ReplayEngine


def _candles(count: int, base_p: float, end_time: datetime) -> list[CandleData]:
    end_ms = int(end_time.timestamp() * 1000)
    return [
        CandleData(
            timestamp_utc=end_ms - (count - i) * 60000,
            open=base_p + i * 2,
            high=base_p + i * 2 + 4,
            low=base_p + i * 2 - 2,
            close=base_p + i * 2 + 1,
            volume=1000.0,
        )
        for i in range(count)
    ]


class TestHIEReplayNoLeakage:

    def test_strict_temporal_cutoff_enforcement(self):
        """
        Populate index with snapshots from Days 1 to 10.
        Execute replay query at Day 5 12:00 UTC.
        Assert that ZERO snapshots from Day 5 12:00 or later are returned.
        """
        store = InMemoryVectorStore()
        replay = ReplayEngine(store)

        base_t = datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc)
        all_snaps = []
        all_outs = []

        # Create 10 daily snapshots
        for day in range(10):
            snap_time = base_t + timedelta(days=day)
            c = _candles(20, 24000.0 + day * 100, snap_time)
            fut_c = _candles(60, c[-1].close, snap_time + timedelta(minutes=60))

            snap = state_builder.build_snapshot("NIFTY", c, snap_time, "1m")
            out = construct_forward_outcomes(snap.snapshot_id, "NIFTY", snap_time, c[-1].close, fut_c)
            all_snaps.append(snap)
            all_outs.append(out)

        replay.load_historical_corpus(all_snaps, all_outs)
        assert store.count() == 10

        # Query strictly at Day 4 12:00 UTC
        query_cutoff = base_t + timedelta(days=4, hours=6)
        query_candles = _candles(20, 24450.0, query_cutoff)
        query_snap = state_builder.build_snapshot("NIFTY", query_candles, query_cutoff, "1m")

        matches = replay.replay_query_at_time(
            query_state=query_snap,
            query_time=query_cutoff,
            top_k=20,
            min_similarity=0.40,
        )

        # Every single retrieved match must have timestamp strictly < query_cutoff
        assert len(matches) > 0
        for m in matches:
            assert m.timestamp < query_cutoff
            # Match cannot be from Days 5, 6, 7, 8, 9
            assert m.timestamp <= base_t + timedelta(days=4)

    def test_reproducible_replay_determinism(self):
        """
        Executing the exact same query against the same historical snapshot corpus
        must produce 100% identical rankings, scores, and forward outcome statistics.
        """
        store = InMemoryVectorStore()
        replay = ReplayEngine(store)

        base_t = datetime(2026, 3, 1, 6, 0, tzinfo=timezone.utc)
        snaps, outs = [], []
        for i in range(5):
            t = base_t + timedelta(hours=i)
            c = _candles(20, 24000 + i * 10, t)
            fut_c = _candles(60, c[-1].close, t + timedelta(minutes=60))
            s = state_builder.build_snapshot("NIFTY", c, t, "1m")
            o = construct_forward_outcomes(s.snapshot_id, "NIFTY", t, c[-1].close, fut_c)
            snaps.append(s)
            outs.append(o)

        replay.load_historical_corpus(snaps, outs)

        q_time = base_t + timedelta(hours=10)
        q_c = _candles(20, 24050, q_time)
        q_snap = state_builder.build_snapshot("NIFTY", q_c, q_time, "1m")

        run1 = replay.replay_query_at_time(q_snap, q_time, top_k=5, min_similarity=0.30)
        run2 = replay.replay_query_at_time(q_snap, q_time, top_k=5, min_similarity=0.30)

        assert len(run1) == len(run2)
        for m1, m2 in zip(run1, run2):
            assert m1.snapshot_id == m2.snapshot_id
            assert m1.similarity_score == m2.similarity_score
            assert m1.outcome_15m.return_pct == m2.outcome_15m.return_pct
            assert m1.outcome_30m.target_hit == m2.outcome_30m.target_hit
