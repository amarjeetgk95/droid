from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import PatternOutcomeDB
from app.models.historical import PatternHitRate, PatternOutcomeRecord


class PatternOutcomeRepository:
    """Async repository for Pattern Outcomes in Supabase PostgreSQL."""

    @staticmethod
    async def save_detection(
        session: AsyncSession,
        symbol: str,
        pattern_type: str,
        pattern_name: str,
        bias: str,
        confidence: float,
        timeframe: str,
        trigger_price: float,
        invalidation_level: float,
        target_level: float,
        regime_state: Optional[str] = None,
        user_id: Optional[UUID] = None,
    ) -> PatternOutcomeDB:
        """Save a detected pattern for outcome tracking."""
        db_record = PatternOutcomeDB(
            user_id=user_id,
            symbol=symbol.upper(),
            pattern_type=pattern_type,
            pattern_name=pattern_name,
            bias=bias,
            confidence=confidence,
            timeframe=timeframe,
            trigger_price=trigger_price,
            invalidation_level=invalidation_level,
            target_level=target_level,
            regime_state=regime_state,
        )
        session.add(db_record)
        await session.commit()
        await session.refresh(db_record)
        return db_record

    @staticmethod
    async def get_unlabeled(
        session: AsyncSession,
        symbol: Optional[str] = None,
        pattern_types: Optional[list[str]] = None,
        timeframe: Optional[str] = None,
        limit: int = 100,
    ) -> list[PatternOutcomeDB]:
        """Fetch patterns that need outcome labeling."""
        stmt = select(PatternOutcomeDB).where(PatternOutcomeDB.outcome_labeled_at.is_(None))

        if symbol:
            stmt = stmt.where(PatternOutcomeDB.symbol == symbol.upper())
        if pattern_types:
            stmt = stmt.where(PatternOutcomeDB.pattern_type.in_(pattern_types))
        if timeframe:
            stmt = stmt.where(PatternOutcomeDB.timeframe == timeframe)

        stmt = stmt.order_by(PatternOutcomeDB.detection_timestamp.asc()).limit(limit)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_outcomes(
        session: AsyncSession,
        outcome_id: UUID,
        outcome_1d: Optional[float] = None,
        outcome_3d: Optional[float] = None,
        outcome_5d: Optional[float] = None,
        hit_target_before_invalidation: Optional[bool] = None,
        outcome_source: str = "background_worker",
    ) -> PatternOutcomeDB:
        """Update a pattern record with computed outcomes."""
        stmt = select(PatternOutcomeDB).where(PatternOutcomeDB.id == outcome_id)
        result = await session.execute(stmt)
        record = result.scalar_one_or_none()
        if not record:
            raise ValueError(f"Pattern outcome {outcome_id} not found")

        if outcome_1d is not None:
            record.outcome_1d = outcome_1d
        if outcome_3d is not None:
            record.outcome_3d = outcome_3d
        if outcome_5d is not None:
            record.outcome_5d = outcome_5d
        if hit_target_before_invalidation is not None:
            record.hit_target_before_invalidation = hit_target_before_invalidation
        record.outcome_labeled_at = datetime.now(timezone.utc)
        record.outcome_source = outcome_source

        await session.commit()
        await session.refresh(record)
        return record

    @staticmethod
    async def get_hit_rates(
        session: AsyncSession,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
    ) -> list[PatternHitRate]:
        """Fetch aggregated hit-rates from materialized view."""
        # Try materialized view first
        try:
            query = """
                SELECT symbol, pattern_type, pattern_name, bias, timeframe,
                       sample_count, avg_return_1d, stddev_return_1d, avg_return_3d,
                       avg_return_5d, hit_target_rate, directional_accuracy,
                       first_detection, last_detection
                FROM pattern_hit_rates
            """
            conditions = []
            params = {}
            if symbol:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol.upper()
            if timeframe:
                conditions.append("timeframe = :timeframe")
                params["timeframe"] = timeframe
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY sample_count DESC"

            result = await session.execute(text(query), params)
            rows = result.mappings().all()

            return [
                PatternHitRate(
                    symbol=row["symbol"],
                    pattern_type=row["pattern_type"],
                    pattern_name=row["pattern_name"],
                    bias=row["bias"],
                    timeframe=row["timeframe"],
                    sample_count=row["sample_count"],
                    avg_return_1d=row["avg_return_1d"],
                    stddev_return_1d=row["stddev_return_1d"],
                    avg_return_3d=row["avg_return_3d"],
                    avg_return_5d=row["avg_return_5d"],
                    hit_target_rate=row["hit_target_rate"],
                    directional_accuracy=row["directional_accuracy"],
                    first_detection=row["first_detection"],
                    last_detection=row["last_detection"],
                )
                for row in rows
            ]
        except Exception:
            # Fallback: compute on the fly from raw table
            query = """
                SELECT
                    symbol, pattern_type, pattern_name, bias, timeframe,
                    COUNT(*) AS sample_count,
                    ROUND(AVG(outcome_1d)::numeric, 4) AS avg_return_1d,
                    ROUND(STDDEV(outcome_1d)::numeric, 4) AS stddev_return_1d,
                    ROUND(AVG(outcome_3d)::numeric, 4) AS avg_return_3d,
                    ROUND(AVG(outcome_5d)::numeric, 4) AS avg_return_5d,
                    ROUND(AVG(CASE WHEN hit_target_before_invalidation THEN 1 ELSE 0 END)::numeric, 4) AS hit_target_rate,
                    ROUND(AVG(CASE WHEN bias = 'BULLISH' AND outcome_1d > 0 THEN 1
                                   WHEN bias = 'BEARISH' AND outcome_1d < 0 THEN 1 ELSE 0 END)::numeric, 4) AS directional_accuracy,
                    MIN(detection_timestamp) AS first_detection,
                    MAX(detection_timestamp) AS last_detection
                FROM pattern_outcomes
                WHERE outcome_labeled_at IS NOT NULL
            """
            conditions = []
            params = {}
            if symbol:
                conditions.append("symbol = :symbol")
                params["symbol"] = symbol.upper()
            if timeframe:
                conditions.append("timeframe = :timeframe")
                params["timeframe"] = timeframe
            if conditions:
                query += " AND " + " AND ".join(conditions)
            query += " GROUP BY symbol, pattern_type, pattern_name, bias, timeframe ORDER BY sample_count DESC"

            result = await session.execute(text(query), params)
            rows = result.mappings().all()

            return [
                PatternHitRate(
                    symbol=row["symbol"],
                    pattern_type=row["pattern_type"],
                    pattern_name=row["pattern_name"],
                    bias=row["bias"],
                    timeframe=row["timeframe"],
                    sample_count=row["sample_count"],
                    avg_return_1d=row["avg_return_1d"],
                    stddev_return_1d=row["stddev_return_1d"],
                    avg_return_3d=row["avg_return_3d"],
                    avg_return_5d=row["avg_return_5d"],
                    hit_target_rate=row["hit_target_rate"],
                    directional_accuracy=row["directional_accuracy"],
                    first_detection=row["first_detection"],
                    last_detection=row["last_detection"],
                )
                for row in rows
            ]

    @staticmethod
    async def get_labeled_outcomes(
        session: AsyncSession,
        symbol: str,
        pattern_types: Optional[list[str]] = None,
        timeframe: Optional[str] = None,
        limit: int = 50,
    ) -> list[PatternOutcomeRecord]:
        """Fetch recent labeled outcomes for a symbol."""
        stmt = (
            select(PatternOutcomeDB)
            .where(PatternOutcomeDB.symbol == symbol.upper())
            .where(PatternOutcomeDB.outcome_labeled_at.is_not(None))
        )
        if pattern_types:
            stmt = stmt.where(PatternOutcomeDB.pattern_type.in_(pattern_types))
        if timeframe:
            stmt = stmt.where(PatternOutcomeDB.timeframe == timeframe)
        stmt = stmt.order_by(PatternOutcomeDB.detection_timestamp.desc()).limit(limit)
        result = await session.execute(stmt)
        records = result.scalars().all()
        return [
            PatternOutcomeRecord(
                id=str(r.id),
                symbol=r.symbol,
                pattern_type=r.pattern_type,
                pattern_name=r.pattern_name,
                bias=r.bias,
                confidence=r.confidence,
                timeframe=r.timeframe,
                trigger_price=r.trigger_price,
                invalidation_level=r.invalidation_level,
                target_level=r.target_level,
                detection_timestamp=r.detection_timestamp,
                regime_state=r.regime_state,
                outcome_1d=r.outcome_1d,
                outcome_3d=r.outcome_3d,
                outcome_5d=r.outcome_5d,
                hit_target_before_invalidation=r.hit_target_before_invalidation,
                outcome_labeled_at=r.outcome_labeled_at,
                outcome_source=r.outcome_source,
            )
            for r in records
        ]

    @staticmethod
    async def refresh_materialized_view(session: AsyncSession) -> None:
        """Refresh the pattern_hit_rates materialized view."""
        await session.execute(text("REFRESH MATERIALIZED VIEW CONCURRENTLY pattern_hit_rates"))
        await session.commit()