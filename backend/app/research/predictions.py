"""Prediction service managing immutable research predictions (§26, N5).

Guarantees:
1. Predictions are immutable after insertion. No UPDATE queries are executed.
2. Forward outcomes are stored in a separate append-only table.
3. Operates gracefully with AsyncSession or fallback in-memory store.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.research.enums import Direction, ForecastHorizon
from app.research.models import PredictionOutcome, ResearchPrediction, ResearchSnapshot

logger = structlog.get_logger(__name__)


class SnapshotService:
    """Service handling point-in-time market-state snapshots (§25).

    P0 (forecast 1h-v2): every persisted forecast must reference the exact
    market state it was computed from. Operates gracefully with an optional
    AsyncSession (Postgres ``research_snapshots``) or fallback in-memory
    store for offline / test operation — mirroring PredictionService.
    """

    # Fallback in-memory storage for offline / test operation
    _memory_snapshots: Dict[str, ResearchSnapshot] = {}

    @classmethod
    async def record_snapshot(
        cls,
        snapshot: ResearchSnapshot,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Persist a point-in-time market snapshot. Never raises on DB failure
        when a session is provided (falls back to memory); raises only when
        the snapshot itself cannot be built/stored in memory, so callers can
        degrade the forecast instead of persisting a prediction without one.
        """
        if not snapshot.snapshot_id:
            snapshot.snapshot_id = f"snap_{uuid.uuid4().hex[:12]}"
        if not snapshot.created_at:
            snapshot.created_at = datetime.now(timezone.utc)

        if len(cls._memory_snapshots) >= 1000:
            oldest_key = next(iter(cls._memory_snapshots))
            cls._memory_snapshots.pop(oldest_key, None)
        cls._memory_snapshots[snapshot.snapshot_id] = snapshot

        if session is not None:
            try:
                stmt = text("""
                    INSERT INTO research_snapshots (
                        snapshot_id, instrument, timeframe, timestamp,
                        price, regime, session, features, options_context,
                        data_quality, created_at
                    ) VALUES (
                        :id, :inst, :tf, :ts, :p, :reg, :sess,
                        CAST(:feat AS jsonb), CAST(:opt AS jsonb), :dq, :created
                    );
                """)
                await session.execute(
                    stmt,
                    {
                        "id": snapshot.snapshot_id,
                        "inst": snapshot.instrument,
                        "tf": snapshot.timeframe,
                        "ts": snapshot.timestamp,
                        "p": snapshot.price,
                        "reg": snapshot.regime,
                        "sess": snapshot.session,
                        "feat": json.dumps(snapshot.features),
                        "opt": json.dumps(snapshot.options_context) if snapshot.options_context else None,
                        "dq": snapshot.data_quality.value if hasattr(snapshot.data_quality, "value") else snapshot.data_quality,
                        "created": snapshot.created_at,
                    }
                )
                await session.commit()
                logger.info("recorded_research_snapshot_db", snapshot_id=snapshot.snapshot_id)
            except Exception as e:
                await session.rollback()
                logger.warning("failed_to_write_snapshot_db_fallback_memory", error=str(e))

        return snapshot.snapshot_id

    @classmethod
    async def get_snapshot(
        cls,
        snapshot_id: str,
        session: Optional[AsyncSession] = None,
    ) -> Optional[ResearchSnapshot]:
        """Fetch a snapshot by ID."""
        if snapshot_id in cls._memory_snapshots:
            return cls._memory_snapshots[snapshot_id]

        if session is not None:
            try:
                stmt = text("SELECT * FROM research_snapshots WHERE snapshot_id = :id")
                result = await session.execute(stmt, {"id": snapshot_id})
                row = result.mappings().first()
                if row:
                    return ResearchSnapshot(**dict(row))
            except Exception as e:
                logger.warning("db_get_snapshot_failed", error=str(e))
        return None


class PredictionService:
    """Service handling prediction recording and outcome appending."""

    # Fallback in-memory storage for offline / test operation
    _memory_predictions: Dict[str, ResearchPrediction] = {}
    _memory_outcomes: Dict[str, PredictionOutcome] = {}

    @classmethod
    async def record_prediction(
        cls,
        prediction: ResearchPrediction,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Record an immutable prediction.
        
        Rule N5: Once written, prediction records CANNOT be updated.
        """
        if not prediction.prediction_id:
            prediction.prediction_id = f"pred_{uuid.uuid4().hex[:12]}"
        if not prediction.created_at:
            prediction.created_at = datetime.now(timezone.utc)

        # Store in memory cache (bounded to prevent memory leaks)
        if len(cls._memory_predictions) >= 1000:
            oldest_key = next(iter(cls._memory_predictions))
            cls._memory_predictions.pop(oldest_key, None)
        cls._memory_predictions[prediction.prediction_id] = prediction

        if session is not None:
            try:
                stmt = text("""
                    INSERT INTO research_predictions (
                        prediction_id, indicator_id, indicator_version,
                        instrument, timeframe, timestamp, current_price,
                        direction, score, confidence, raw_value, normalized_value,
                        component_values, forecast_horizon, horizon_candles,
                        target_price, invalidation_price, snapshot_id, created_at
                    ) VALUES (
                        :prediction_id, :indicator_id, :indicator_version,
                        :instrument, :timeframe, :timestamp, :current_price,
                        :direction, :score, :confidence, CAST(:raw_value AS jsonb), :normalized_value,
                        CAST(:component_values AS jsonb), :forecast_horizon, :horizon_candles,
                        :target_price, :invalidation_price, :snapshot_id, :created_at
                    );
                """)
                await session.execute(
                    stmt,
                    {
                        "prediction_id": prediction.prediction_id,
                        "indicator_id": prediction.indicator_id,
                        "indicator_version": prediction.indicator_version,
                        "instrument": prediction.instrument,
                        "timeframe": prediction.timeframe,
                        "timestamp": prediction.timestamp,
                        "current_price": prediction.current_price,
                        "direction": prediction.direction.value if isinstance(prediction.direction, Direction) else prediction.direction,
                        "score": prediction.score,
                        "confidence": prediction.confidence,
                        "raw_value": json.dumps(prediction.raw_value) if prediction.raw_value is not None else None,
                        "normalized_value": prediction.normalized_value,
                        "component_values": json.dumps(prediction.component_values),
                        "forecast_horizon": prediction.forecast_horizon.value if isinstance(prediction.forecast_horizon, ForecastHorizon) else prediction.forecast_horizon,
                        "horizon_candles": prediction.horizon_candles,
                        "target_price": prediction.target_price,
                        "invalidation_price": prediction.invalidation_price,
                        "snapshot_id": prediction.snapshot_id,
                        "created_at": prediction.created_at,
                    }
                )
                await session.commit()
                logger.info("recorded_immutable_prediction_db", prediction_id=prediction.prediction_id)
            except Exception as e:
                await session.rollback()
                logger.warning("failed_to_write_prediction_db_fallback_memory", error=str(e))

        return prediction.prediction_id

    @classmethod
    async def append_outcome(
        cls,
        outcome: PredictionOutcome,
        session: Optional[AsyncSession] = None,
    ) -> str:
        """Append an outcome to an existing prediction.
        
        Appends to research_prediction_outcomes without mutating research_predictions.
        """
        if not outcome.outcome_id:
            outcome.outcome_id = f"out_{uuid.uuid4().hex[:12]}"
        if not outcome.evaluated_at:
            outcome.evaluated_at = datetime.now(timezone.utc)

        # Store in memory cache (bounded to prevent memory leaks)
        if len(cls._memory_outcomes) >= 1000:
            oldest_key = next(iter(cls._memory_outcomes))
            cls._memory_outcomes.pop(oldest_key, None)
        cls._memory_outcomes[outcome.prediction_id] = outcome

        if session is not None:
            try:
                stmt = text("""
                    INSERT INTO research_prediction_outcomes (
                        outcome_id, prediction_id, actual_direction,
                        actual_price_move, actual_pct_move, entry_price,
                        exit_price, mfe, mae, target_hit, stop_hit,
                        time_to_target_sec, is_correct, evaluated_at
                    ) VALUES (
                        :outcome_id, :prediction_id, :actual_direction,
                        :actual_price_move, :actual_pct_move, :entry_price,
                        :exit_price, :mfe, :mae, :target_hit, :stop_hit,
                        :time_to_target_sec, :is_correct, :evaluated_at
                    )
                    ON CONFLICT (prediction_id) DO NOTHING;
                """)
                await session.execute(
                    stmt,
                    {
                        "outcome_id": outcome.outcome_id,
                        "prediction_id": outcome.prediction_id,
                        "actual_direction": outcome.actual_direction.value if isinstance(outcome.actual_direction, Direction) else outcome.actual_direction,
                        "actual_price_move": outcome.actual_price_move,
                        "actual_pct_move": outcome.actual_pct_move,
                        "entry_price": outcome.entry_price,
                        "exit_price": outcome.exit_price,
                        "mfe": outcome.mfe,
                        "mae": outcome.mae,
                        "target_hit": outcome.target_hit,
                        "stop_hit": outcome.stop_hit,
                        "time_to_target_sec": outcome.time_to_target_sec,
                        "is_correct": outcome.is_correct,
                        "evaluated_at": outcome.evaluated_at,
                    }
                )
                await session.commit()
                logger.info("appended_prediction_outcome_db", outcome_id=outcome.outcome_id)
            except Exception as e:
                await session.rollback()
                logger.warning("failed_to_append_outcome_db_fallback_memory", error=str(e))

        return outcome.outcome_id

    @classmethod
    async def get_prediction(
        cls,
        prediction_id: str,
        session: Optional[AsyncSession] = None,
    ) -> Optional[ResearchPrediction]:
        """Fetch a prediction by ID."""
        if prediction_id in cls._memory_predictions:
            return cls._memory_predictions[prediction_id]

        if session is not None:
            stmt = text("SELECT * FROM research_predictions WHERE prediction_id = :id")
            result = await session.execute(stmt, {"id": prediction_id})
            row = result.mappings().first()
            if row:
                return ResearchPrediction(**dict(row))
        return None

    @classmethod
    async def get_outcome(
        cls,
        prediction_id: str,
        session: Optional[AsyncSession] = None,
    ) -> Optional[PredictionOutcome]:
        """Fetch the outcome for a prediction."""
        if prediction_id in cls._memory_outcomes:
            return cls._memory_outcomes[prediction_id]

        if session is not None:
            stmt = text("SELECT * FROM research_prediction_outcomes WHERE prediction_id = :id")
            result = await session.execute(stmt, {"id": prediction_id})
            row = result.mappings().first()
            if row:
                return PredictionOutcome(**dict(row))
        return None

    @classmethod
    async def list_predictions(
        cls,
        indicator_id: Optional[str] = None,
        instrument: Optional[str] = None,
        limit: int = 50,
        session: Optional[AsyncSession] = None,
    ) -> List[ResearchPrediction]:
        """List predictions with optional filters."""
        if session is not None:
            try:
                query = "SELECT * FROM research_predictions WHERE 1=1"
                params: Dict[str, Any] = {"limit": limit}
                if indicator_id:
                    query += " AND indicator_id = :ind_id"
                    params["ind_id"] = indicator_id
                if instrument:
                    query += " AND instrument = :inst"
                    params["inst"] = instrument
                query += " ORDER BY timestamp DESC LIMIT :limit"
                result = await session.execute(text(query), params)
                rows = result.mappings().all()
                return [ResearchPrediction(**dict(r)) for r in rows]
            except Exception as e:
                logger.warning("db_list_predictions_failed_fallback_memory", error=str(e))

        # Memory filter fallback
        preds = list(cls._memory_predictions.values())
        if indicator_id:
            preds = [p for p in preds if p.indicator_id == indicator_id]
        if instrument:
            preds = [p for p in preds if p.instrument == instrument]
        return sorted(preds, key=lambda x: x.timestamp, reverse=True)[:limit]
