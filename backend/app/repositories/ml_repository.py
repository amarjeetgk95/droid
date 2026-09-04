from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import MLPredictionDB
from app.models.ml import MLPredictionResponse


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
        )
        session.add(db_record)
        await session.commit()
        await session.refresh(db_record)
        return db_record

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
