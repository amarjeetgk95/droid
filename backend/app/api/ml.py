from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.ml.predictor import ml_predictor
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="xgboost_lightgbm_ensemble",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.get("/predict/{symbol}")
async def get_ml_prediction(symbol: str):
    """Retrieve probabilistic ML directional forecast (Bullish/Neutral/Bearish %) and trend strength."""
    try:
        prediction = await ml_predictor.predict_probabilities(symbol)
        return {
            "data": prediction.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
