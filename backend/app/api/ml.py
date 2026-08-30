from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.ml.predictor import ml_predictor
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])


def _make_meta() -> ApiMeta:
    try:
        from app.ml.trainer import META_PATH

        if META_PATH.exists():
            return ApiMeta(
                provider="xgboost_lightgbm_ensemble",
                timestamp=datetime.now(timezone.utc),
                status=DataStatus.DEMO,
            )
    except Exception:
        pass
    return ApiMeta(
        provider="xgboost_lightgbm_ensemble",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.post("/train")
async def train_ml_ensemble(n_samples: int = 2000):
    """Train XGBoost + LightGBM ensemble on synthetic (or historical) data."""
    from app.ml.trainer import train_ensemble

    try:
        meta = await train_ensemble(n_samples=n_samples)
        return {"data": meta, "error": None, "meta": _make_meta().model_dump()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/model-info")
async def get_model_info():
    """Get current ensemble model metadata."""
    from app.ml.trainer import META_PATH, XGB_PATH, LGB_PATH
    import json

    if not META_PATH.exists():
        return {"data": {"trained": False, "message": "No trained ensemble found. Use POST /api/v1/ml/train"}, "error": None, "meta": _make_meta().model_dump()}
    meta = json.loads(META_PATH.read_text())
    meta["artifacts"] = {
        "xgb_exists": XGB_PATH.exists(),
        "lgb_exists": LGB_PATH.exists(),
        "xgb_size_bytes": XGB_PATH.stat().st_size if XGB_PATH.exists() else 0,
        "lgb_size_bytes": LGB_PATH.stat().st_size if LGB_PATH.exists() else 0,
    }
    return {"data": meta, "error": None, "meta": _make_meta().model_dump()}


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
