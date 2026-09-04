"""
HIE Supabase PostgreSQL Persistence Layer — §§3.1, 4, 11, 36
Persists Historical State Snapshots, Forward Outcomes, and Query Audits to Supabase.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
import structlog
from sqlalchemy import text

from app.core.database import get_async_session_factory
from app.historical_intelligence.schemas import HistoricalStateSnapshot, HistoricalOutcomeRecord

logger = structlog.get_logger()


async def persist_hie_snapshot(snapshot: HistoricalStateSnapshot) -> bool:
    """Upsert a point-in-time HistoricalStateSnapshot into hie_state_snapshots."""
    factory = get_async_session_factory()
    if factory is None:
        return False

    try:
        raw_feat = snapshot.canonical_features.to_flat_dict() if hasattr(snapshot, "canonical_features") else {}
        norm_feat = snapshot.normalized_features.normalized_dict if hasattr(snapshot, "normalized_features") else {}
        embedding = snapshot.embedding if hasattr(snapshot, "embedding") and snapshot.embedding else [0.0] * 32

        # Ensure trading_date is date format (YYYY-MM-DD)
        td = snapshot.trading_date
        if isinstance(td, datetime):
            td_str = td.strftime("%Y-%m-%d")
        elif isinstance(td, str) and len(td) >= 10:
            td_str = td[:10]
        else:
            td_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        query = text("""
            INSERT INTO hie_state_snapshots (
                snapshot_id, instrument, timeframe, timestamp, trading_date, session,
                minute_of_session, market_regime, volatility_regime, vix_bucket,
                data_quality_score, feature_version, embedding_version,
                raw_features_json, normalized_features_json, embedding_vector, created_at
            ) VALUES (
                :snapshot_id, :instrument, :timeframe, :timestamp, CAST(:trading_date AS DATE), :session,
                :minute_of_session, :market_regime, :volatility_regime, :vix_bucket,
                :data_quality_score, :feature_version, :embedding_version,
                CAST(:raw_features_json AS JSONB), CAST(:normalized_features_json AS JSONB), :embedding_vector, now()
            )
            ON CONFLICT (snapshot_id) DO UPDATE SET
                data_quality_score = EXCLUDED.data_quality_score,
                raw_features_json = EXCLUDED.raw_features_json,
                normalized_features_json = EXCLUDED.normalized_features_json;
        """)

        params = {
            "snapshot_id": snapshot.snapshot_id,
            "instrument": snapshot.instrument,
            "timeframe": snapshot.timeframe,
            "timestamp": snapshot.timestamp,
            "trading_date": td_str,
            "session": snapshot.session.value if hasattr(snapshot.session, "value") else str(snapshot.session),
            "minute_of_session": getattr(snapshot, "minute_of_session", 0),
            "market_regime": snapshot.market_regime.value if hasattr(snapshot.market_regime, "value") else str(snapshot.market_regime),
            "volatility_regime": snapshot.volatility_regime.value if hasattr(snapshot.volatility_regime, "value") else str(snapshot.volatility_regime),
            "vix_bucket": snapshot.vix_bucket.value if hasattr(snapshot.vix_bucket, "value") else str(snapshot.vix_bucket),
            "data_quality_score": float(getattr(snapshot, "data_quality_score", 1.0)),
            "feature_version": getattr(snapshot, "feature_version", "1.0.0"),
            "embedding_version": getattr(snapshot, "embedding_version", "1.0.0"),
            "raw_features_json": json.dumps(raw_feat),
            "normalized_features_json": json.dumps(norm_feat),
            "embedding_vector": embedding,
        }

        async with factory() as session:
            await session.execute(query, params)
            await session.commit()
            logger.debug("hie_snapshot_persisted", snapshot_id=snapshot.snapshot_id)
            return True
    except Exception as e:
        logger.warning("persist_hie_snapshot_failed", snapshot_id=snapshot.snapshot_id, error=str(e)[:250])
        return False


async def persist_hie_query_audit(
    instrument: str,
    timeframe: str,
    query_mode: str,
    sample_count: int,
    effective_sample_size: float,
    bullish_prob: float,
    confidence: float | str,
    latency_ms: float,
) -> bool:
    """Insert query audit log into hie_query_audit table in Supabase."""
    factory = get_async_session_factory()
    if factory is None:
        return False

    try:
        conf_num = float(confidence) if isinstance(confidence, (int, float)) else (85.0 if confidence == "HIGH" else (65.0 if confidence == "MEDIUM" else 45.0))
        query = text("""
            INSERT INTO hie_query_audit (
                instrument, timeframe, query_mode, sample_count,
                effective_sample_size, bullish_prob, confidence, latency_ms, created_at
            ) VALUES (
                :instrument, :timeframe, :query_mode, :sample_count,
                :effective_sample_size, :bullish_prob, :confidence, :latency_ms, now()
            )
        """)
        params = {
            "instrument": instrument,
            "timeframe": timeframe,
            "query_mode": query_mode,
            "sample_count": sample_count,
            "effective_sample_size": float(effective_sample_size),
            "bullish_prob": float(bullish_prob),
            "confidence": conf_num,
            "latency_ms": float(latency_ms),
        }

        async with factory() as session:
            await session.execute(query, params)
            await session.commit()
            logger.debug("hie_query_audit_persisted", instrument=instrument)
            return True
    except Exception as e:
        logger.warning("persist_hie_query_audit_failed", instrument=instrument, error=str(e)[:250])
        return False
