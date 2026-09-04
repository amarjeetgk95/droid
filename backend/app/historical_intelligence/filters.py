"""
Hierarchical Metadata Pre-Filtering Engine — §§10, 13, 32
Builds query filters for Qdrant and in-memory ANN vector indexes.
"""
from __future__ import annotations

from datetime import timezone
from typing import Any, Callable
from app.historical_intelligence.schemas import (
    HistoricalStateSnapshot,
    HistoricalQuery,
    MarketRegime,
)


class MetadataFilterBuilder:
    """
    Builds structured pre-filter criteria ensuring hierarchical candidate reduction
    and zero lookahead enforcement (snapshot_time < query_time T).
    """

    @staticmethod
    def build_qdrant_filter(query: HistoricalQuery) -> dict[str, Any]:
        """Generate Qdrant JSON filter payload matching Qdrant query syntax."""
        must_clauses: list[dict[str, Any]] = [
            {"key": "instrument", "match": {"value": query.instrument.upper()}},
            {"key": "timeframe", "match": {"value": query.timeframe.lower()}},
            {"key": "data_quality_score", "range": {"gte": 0.80}},
        ]

        # Temporal Cutoff (§32: Lookahead Prevention)
        if query.temporal_cutoff is not None:
            cutoff_ts = int(query.temporal_cutoff.timestamp())
            must_clauses.append({"key": "timestamp_epoch", "range": {"lt": cutoff_ts}})

        # Hierarchical Constraints (§13)
        if query.regime_filter is not None and query.regime_filter != MarketRegime.UNKNOWN:
            must_clauses.append({"key": "regime", "match": {"value": query.regime_filter.value}})

        if query.session_filter is not None:
            must_clauses.append({"key": "session", "match": {"value": query.session_filter.value}})

        if query.volatility_filter is not None:
            must_clauses.append({"key": "volatility_regime", "match": {"value": query.volatility_filter.value}})

        return {"must": must_clauses}

    @staticmethod
    def build_in_memory_predicate(query: HistoricalQuery) -> Callable[[HistoricalStateSnapshot], bool]:
        """Generate high-speed Python boolean predicate for in-memory / testing / offline indexing."""
        inst = query.instrument.upper()
        tf = query.timeframe.lower()
        cutoff_dt = query.temporal_cutoff
        reg = query.regime_filter
        sess = query.session_filter
        vol = query.volatility_filter

        def _predicate(snap: HistoricalStateSnapshot) -> bool:
            # 1. Base identity
            if snap.instrument.upper() != inst:
                return False
            if snap.timeframe.lower() != tf:
                return False
            if snap.data_quality_score < 0.80:
                return False

            # 2. Strict lookahead prevention: snapshot_time < query_time T (§32)
            if cutoff_dt is not None:
                # Normalize tz
                s_ts = snap.timestamp.astimezone(timezone.utc) if snap.timestamp.tzinfo else snap.timestamp.replace(tzinfo=timezone.utc)
                c_ts = cutoff_dt.astimezone(timezone.utc) if cutoff_dt.tzinfo else cutoff_dt.replace(tzinfo=timezone.utc)
                if s_ts >= c_ts:
                    return False

            # 3. Hierarchical filters (§13)
            if reg is not None and reg != MarketRegime.UNKNOWN:
                bull_pair = {MarketRegime.TRENDING_BULLISH, MarketRegime.BREAKOUT}
                bear_pair = {MarketRegime.TRENDING_BEARISH, MarketRegime.BREAKDOWN}
                if reg in bull_pair and snap.market_regime not in bull_pair:
                    return False
                elif reg in bear_pair and snap.market_regime not in bear_pair:
                    return False
                elif reg not in bull_pair and reg not in bear_pair and snap.market_regime != reg:
                    return False

            if sess is not None and snap.session != sess:
                return False
            if vol is not None and snap.volatility_regime != vol:
                return False

            return True

        return _predicate
