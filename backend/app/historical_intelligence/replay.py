"""
Deterministic Replay & Temporal Leakage Guard — §§31, 32
Reconstructs historical intelligence deterministically with strict T < query_time enforcement.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, List
from app.historical_intelligence.schemas import (
    HistoricalStateSnapshot,
    HistoricalOutcomeRecord,
    HistoricalQuery,
    HistoricalAnalogMatch,
)
from app.historical_intelligence.retriever import InMemoryVectorStore


class ReplayEngine:
    """
    Enforces deterministic replay without lookahead leakage.
    At query_time = T, only states strictly before T (snapshot_time < T) are visible.
    """

    def __init__(self, vector_store: Optional[InMemoryVectorStore] = None):
        self.vector_store = vector_store or InMemoryVectorStore()

    def load_historical_corpus(
        self,
        snapshots: list[HistoricalStateSnapshot],
        outcomes: list[HistoricalOutcomeRecord],
    ):
        """Loads historical states and outcomes into replay index."""
        outcome_map = {o.snapshot_id: o for o in outcomes}
        for s in snapshots:
            self.vector_store.upsert(s, outcome_map.get(s.snapshot_id))

    def replay_query_at_time(
        self,
        query_state: HistoricalStateSnapshot,
        query_time: datetime,
        top_k: int = 50,
        min_similarity: float = 0.65,
    ) -> list[HistoricalAnalogMatch]:
        """
        Executes query strictly at point-in-time T.
        Enforces: candidate.timestamp < query_time.
        """
        q_time_utc = query_time.astimezone(timezone.utc) if query_time.tzinfo else query_time.replace(tzinfo=timezone.utc)

        query = HistoricalQuery(
            instrument=query_state.instrument,
            timeframe=query_state.timeframe,
            top_k=top_k,
            min_similarity=min_similarity,
            temporal_cutoff=q_time_utc,
            regime_filter=query_state.market_regime,
        )

        matches = self.vector_store.search(query_state, query)

        # Verification assertion (§32)
        for m in matches:
            m_utc = m.timestamp.astimezone(timezone.utc) if m.timestamp.tzinfo else m.timestamp.replace(tzinfo=timezone.utc)
            if m_utc >= q_time_utc:
                raise RuntimeError(
                    f"CRITICAL LOOKAHEAD LEAKAGE: Retrieved analogue at {m_utc} >= Query Time {q_time_utc}"
                )

        return matches
