from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import envelope
from app.core.database import get_db_session
from app.core.security import AuthUser, get_current_user
from app.ml.predictor import ml_predictor
from app.ml.targets import (
    DEFAULT_HORIZON_MINUTES,
    SUPPORTED_HORIZONS,
    TARGET_SPEC_VERSION,
    describe_target,
)
from app.models.market import DataStatus

router = APIRouter(prefix="/api/v1/ml", tags=["ml"])

_PROVIDER = "xgboost_lightgbm_ensemble"


class TrainRequest(BaseModel):
    features: list[list[float]] = Field(..., description="Historical feature vectors, minimum 100 samples")
    labels: list[int] = Field(..., description="Labels: 0=BEARISH, 1=NEUTRAL, 2=BULLISH")
    horizon_minutes: int = Field(
        default=DEFAULT_HORIZON_MINUTES,
        description=f"Target horizon. Supported: {list(SUPPORTED_HORIZONS)}",
    )
    target_spec_version: str = Field(
        default=TARGET_SPEC_VERSION,
        description="Label definition version (must match trainer spec)",
    )


class SettleRequest(BaseModel):
    prediction_id: str = Field(..., description="ml_predictions.id (UUID)")
    outcome_spot: float = Field(..., description="Realized spot at T+H. Must be > 0.")
    atr_at_t: float = Field(..., description="ATR at prediction time. Must be > 0.")
    spot_at_t: float = Field(..., description="Spot at prediction time. Must be > 0.")


@router.post("/train")
async def train_ml_ensemble(
    request: TrainRequest,
    user: AuthUser | None = Depends(get_current_user),
):
    """Train XGBoost + LightGBM ensemble on verified historical feature vectors."""
    from app.ml.trainer import train_ensemble

    try:
        meta = await train_ensemble(
            features=request.features,
            labels=request.labels,
            horizon_minutes=request.horizon_minutes,
            target_spec_version=request.target_spec_version,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return envelope(meta, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/model-info")
async def get_model_info():
    """Get current ensemble model metadata."""
    from app.ml.trainer import META_PATH, XGB_PATH, LGB_PATH
    import json

    if not META_PATH.exists():
        return envelope(
            {"trained": False, "message": "No trained ensemble found. Use POST /api/v1/ml/train"},
            provider=_PROVIDER,
            status=DataStatus.OFFLINE,
        )
    meta = json.loads(META_PATH.read_text())
    meta["artifacts"] = {
        "xgb_exists": XGB_PATH.exists(),
        "lgb_exists": LGB_PATH.exists(),
        "xgb_size_bytes": XGB_PATH.stat().st_size if XGB_PATH.exists() else 0,
        "lgb_size_bytes": LGB_PATH.stat().st_size if LGB_PATH.exists() else 0,
    }
    return envelope(meta, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/predict/{symbol}")
async def get_ml_prediction(
    symbol: str,
    horizon_minutes: int = Query(
        default=DEFAULT_HORIZON_MINUTES,
        description=f"Forward horizon in minutes. Supported: {list(SUPPORTED_HORIZONS)}",
    ),
):
    """Retrieve probabilistic ML directional forecast for horizon H.

    Unsupported horizons return 400 — never silently remapped. Horizons
    without a matching trained artifact are served by the shared snapshot
    model with calibrated=false.
    """
    try:
        prediction = await ml_predictor.predict_probabilities(symbol, horizon_minutes=horizon_minutes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return envelope(prediction, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/targets")
async def get_target_specs():
    """Versioned label definitions per horizon (auditability for training)."""
    return envelope(
        {
            "target_spec_version": TARGET_SPEC_VERSION,
            "supported_horizons": list(SUPPORTED_HORIZONS),
            "default_horizon_minutes": DEFAULT_HORIZON_MINUTES,
            "specs": [describe_target(h) for h in SUPPORTED_HORIZONS],
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.post("/outcomes/settle")
async def settle_ml_outcome(
    request: SettleRequest,
    session: AsyncSession = Depends(get_db_session),
    user: AuthUser | None = Depends(get_current_user),
):
    """Settle one prediction with its realized forward spot (append-only)."""
    from uuid import UUID

    from app.repositories.ml_repository import MLRepository

    try:
        prediction_id = UUID(str(request.prediction_id))
    except ValueError:
        raise HTTPException(status_code=400, detail="prediction_id must be a UUID")
    try:
        rec = await MLRepository.settle_outcome(
            session,
            prediction_id,
            outcome_spot=request.outcome_spot,
            atr_at_t=request.atr_at_t,
            spot_at_t=request.spot_at_t,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if rec is None:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return envelope(
        {
            "id": str(rec.id),
            "outcome_label": rec.outcome_label,
            "outcome_spot": rec.outcome_spot,
            "settled_at": rec.settled_at.isoformat() if rec.settled_at else None,
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.get("/calibration/{symbol}")
async def get_ml_calibration(
    symbol: str,
    horizon_minutes: int | None = Query(default=None),
    session: AsyncSession = Depends(get_db_session),
):
    """Per-(horizon, bias) hit-rates over settled predictions.

    Unsettleable/unsettled rows are excluded (counts visible via n).
    Hit-rate on <30 samples is noise — check n before trusting a cell.
    """
    from app.ml.calibration import summarize_calibration
    from app.ml.targets import validate_horizon
    from app.repositories.ml_repository import MLRepository

    if horizon_minutes is not None:
        try:
            validate_horizon(horizon_minutes)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    rows = await MLRepository.get_settled_rows(session, symbol, horizon_minutes)
    return envelope(summarize_calibration(rows), provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/settle/run")
async def run_ml_settlement(
    symbol: str | None = Query(default=None, description="Limit to one symbol"),
    limit: int = Query(default=100, ge=1, le=1000),
    session: AsyncSession = Depends(get_db_session),
    user: AuthUser | None = Depends(get_current_user),
):
    """Auto-settle predictions whose horizon has elapsed (Phase 1).

    Session-crossing NSE windows are skipped as INSUFFICIENT_DATA, never
    bridged. Call on a schedule (cron) — e.g. every 15m — plus on demand.
    """
    from app.ml.settlement import settle_due

    summary = await settle_due(session, symbol=symbol, limit=limit)
    return envelope(summary, provider=_PROVIDER, status=DataStatus.OFFLINE)
