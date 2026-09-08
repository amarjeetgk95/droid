from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import MLPredictionDB
from app.models.ml import MLPredictionResponse
from app.ml.targets import TARGET_SPEC_VERSION


class MLRepository:
    """Async repository for ML Predictions in Supabase PostgreSQL."""

    @staticmethod
    async def save_prediction(
        session: AsyncSession,
        prediction: MLPredictionResponse,
    ) -> MLPredictionDB:
        """Save a computed ML prediction record."""
        features_json = [f.model_dump() for f in prediction.top_features]
        db_record = MLPredictionDB(
            symbol=prediction.symbol,
            timestamp=prediction.timestamp,
            spot_price=prediction.spot_price,
            bullish_pct=prediction.bullish_pct,
            neutral_pct=prediction.neutral_pct,
            bearish_pct=prediction.bearish_pct,
            trend_strength=prediction.trend_strength,
            confidence_score=prediction.confidence_score,
            predicted_bias=prediction.predicted_bias,
            market_regime=prediction.market_regime,
            top_features=features_json,
            model_version=prediction.model_version,
            horizon_minutes=prediction.horizon_minutes,
            target_spec_version=prediction.target_spec_version,
            model_source=prediction.model_source,
            atr_at_t=prediction.atr_at_t,
        )
        session.add(db_record)
        await session.commit()
        await session.refresh(db_record)
        return db_record

    @staticmethod
    async def settle_outcome(
        session: AsyncSession,
        prediction_id,
        outcome_spot: float,
        atr_at_t: float,
        spot_at_t: float,
    ) -> MLPredictionDB | None:
        """Settle one prediction with its realized forward spot.

        Labels via the CURRENT target spec; refuses to overwrite an already
        settled row so outcomes stay append-only.
        """
        from app.ml.calibration import settle_prediction

        rec = await session.get(MLPredictionDB, prediction_id)
        if rec is None or rec.outcome_label is not None:
            return rec
        settled = settle_prediction(spot_at_t, outcome_spot, atr_at_t)
        rec.outcome_label = settled["outcome_label"]
        rec.outcome_spot = outcome_spot
        rec.settled_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(rec)
        return rec

    @staticmethod
    async def get_settled_rows(
        session: AsyncSession,
        symbol: str,
        horizon_minutes: int | None = None,
        limit: int = 2000,
    ) -> list[dict]:
        """Fetch settled rows as plain dicts for calibration aggregation."""
        stmt = (
            select(MLPredictionDB)
            .where(MLPredictionDB.symbol == symbol.upper())
            .where(MLPredictionDB.outcome_label.is_not(None))
            .order_by(MLPredictionDB.timestamp.desc())
            .limit(limit)
        )
        if horizon_minutes is not None:
            stmt = stmt.where(MLPredictionDB.horizon_minutes == horizon_minutes)
        result = await session.execute(stmt)
        from app.ml.targets import INV_LABEL

        rows = []
        for r in result.scalars().all():
            rows.append(
                {
                    "symbol": r.symbol,
                    "horizon_minutes": r.horizon_minutes,
                    "predicted_bias": r.predicted_bias,
                    "outcome_name": INV_LABEL.get(r.outcome_label),
                    "confidence_score": r.confidence_score,
                    "target_spec_version": r.target_spec_version or TARGET_SPEC_VERSION,
                }
            )
        return rows

    @staticmethod
    async def get_latest_predictions(
        session: AsyncSession,
        symbol: str,
        limit: int = 20,
    ) -> list[MLPredictionDB]:
        """Fetch historical ML predictions for a symbol."""
        stmt = (
            select(MLPredictionDB)
            .where(MLPredictionDB.symbol == symbol.upper())
            .order_by(MLPredictionDB.timestamp.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())
