"""Research Laboratory API Endpoints (§45).

Provides isolated endpoints for chart intelligence, indicator registry,
offline validation, feature computation, and immutable predictions.
Architecturally separated from production signal generation.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import uuid
import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.research.enums import (
    DataQualityStatus,
    Direction,
    ExperimentStatus,
    ForecastHorizon,
    IndicatorCategory,
    IndicatorLifecycle,
    MarketRegime,
)
from app.research.features import FeatureLayer
from app.research.models import (
    ExperimentDefinition,
    ExperimentRun,
    IndicatorContext,
    IndicatorDefinition,
    IndicatorOutput,
    PredictionOutcome,
    ResearchAnnotation,
    ResearchPrediction,
    ResearchSnapshot,
    ValidationReport,
)
from app.research.options_context import ResearchOptionsContext
from app.research.outcome_measurer import OutcomeMeasurer
from app.research.predictions import PredictionService
from app.research.registry import IndicatorRegistry
from app.research.validation.backtest_engine import CheapValidationGate
from app.services.market_service import MarketService

logger = structlog.get_logger(__name__)

router = APIRouter(prefix="/api/v1/research", tags=["Research Laboratory"])


# -------------------------------------------------------------
# Request / Response Schemas
# -------------------------------------------------------------
class CalculateIndicatorRequest(BaseModel):
    instrument: str = Field(default="NIFTY 50")
    timeframe: str = Field(default="5m")
    parameters: Dict[str, Any] = Field(default_factory=dict)
    candles: Optional[List[Dict[str, Any]]] = None


class RunExperimentRequest(BaseModel):
    indicator_id: str
    instrument: str = Field(default="NIFTY 50")
    timeframe: str = Field(default="5m")
    horizon_candles: int = Field(default=5, ge=1, le=50)
    stride: int = Field(default=5, ge=1, le=20)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    candles: Optional[List[Dict[str, Any]]] = None


class SnapshotCreateRequest(BaseModel):
    instrument: str
    timeframe: str
    price: float
    regime: Optional[str] = None
    session: Optional[str] = None
    features: Dict[str, Any] = Field(default_factory=dict)
    options_context: Optional[Dict[str, Any]] = None
    data_quality: DataQualityStatus = DataQualityStatus.LIVE


class MeasurePredictionRequest(BaseModel):
    forward_candles: Optional[List[Dict[str, Any]]] = None


# Helper to convert NormalizedCandle to dict
def _candle_to_dict(c: Any) -> Dict[str, Any]:
    if isinstance(c, dict):
        return c
    return {
        "open": float(getattr(c, "open", 0.0)),
        "high": float(getattr(c, "high", 0.0)),
        "low": float(getattr(c, "low", 0.0)),
        "close": float(getattr(c, "close", 0.0)),
        "volume": float(getattr(c, "volume", 0.0) or 0.0),
        "timestamp": getattr(c, "timestamp", datetime.now(timezone.utc)).isoformat()
        if hasattr(getattr(c, "timestamp", None), "isoformat")
        else str(getattr(c, "timestamp", "")),
    }


# -------------------------------------------------------------
# 1. Chart & Features (§10, §12)
# -------------------------------------------------------------
@router.get("/chart/state")
async def get_chart_state(
    instrument: str = Query("NIFTY 50", description="Trading instrument"),
    timeframe: str = Query("5m", description="Candle timeframe"),
):
    """Fetch current market state and latest candles for the research chart."""
    ms = MarketService()
    try:
        quote = await ms.get_quote(instrument)
        raw_candles = await ms.get_candles(instrument, timeframe=timeframe)
        candles = [_candle_to_dict(c) for c in raw_candles] if raw_candles else []

        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "current_price": quote.ltp if quote else None,
            "change_pct": quote.change_percent if quote else None,
            "candles_count": len(candles),
            "latest_candle": candles[-1] if candles else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.warning("get_chart_state_failed", instrument=instrument, error=str(e))
        return {
            "instrument": instrument,
            "timeframe": timeframe,
            "current_price": None,
            "change_pct": None,
            "candles_count": 0,
            "latest_candle": None,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/chart/features")
async def get_chart_features(
    instrument: str = Query("NIFTY 50"),
    timeframe: str = Query("5m"),
):
    """Compute and return unified feature layer for the requested instrument and timeframe."""
    ms = MarketService()
    try:
        raw_candles = await ms.get_candles(instrument, timeframe=timeframe)
        candles = [_candle_to_dict(c) for c in raw_candles] if raw_candles else []
        options_ctx = await ResearchOptionsContext.get_context(instrument)

        if not candles:
            return {"error": f"No candles available for {instrument} {timeframe}"}

        features = FeatureLayer.compute_features(
            instrument=instrument,
            timeframe=timeframe,
            candles=candles,
            options_ctx=options_ctx,
        )
        return features
    except Exception as e:
        logger.error("get_chart_features_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# -------------------------------------------------------------
# 2. Options Context (§11)
# -------------------------------------------------------------
@router.get("/options-context")
async def get_options_context(
    instrument: str = Query("NIFTY 50"),
):
    """Fetch read-only options context snapshot."""
    return await ResearchOptionsContext.get_context(instrument)


# -------------------------------------------------------------
# 3. Indicator Registry (§13, §14)
# -------------------------------------------------------------
@router.get("/indicators", response_model=List[IndicatorDefinition])
async def list_indicators(
    category: Optional[IndicatorCategory] = None,
    lifecycle: Optional[IndicatorLifecycle] = None,
):
    """List all registered research indicators."""
    if category:
        return IndicatorRegistry.get_by_category(category)
    if lifecycle:
        return IndicatorRegistry.get_by_lifecycle(lifecycle)
    return IndicatorRegistry.list_all()


@router.get("/indicators/{indicator_id}", response_model=IndicatorDefinition)
async def get_indicator(indicator_id: str):
    """Retrieve metadata definition for a specific indicator."""
    ind = IndicatorRegistry.get(indicator_id)
    if not ind:
        raise HTTPException(status_code=404, detail=f"Indicator '{indicator_id}' not found")
    return ind.get_definition()


@router.post("/indicators/{indicator_id}/calculate", response_model=IndicatorOutput)
async def calculate_indicator(
    indicator_id: str,
    body: CalculateIndicatorRequest = Body(...),
):
    """Run indicator calculation on current market candles or custom supplied series."""
    ind = IndicatorRegistry.get(indicator_id)
    if not ind:
        raise HTTPException(status_code=404, detail=f"Indicator '{indicator_id}' not found")

    candles = body.candles
    if not candles:
        ms = MarketService()
        raw_candles = await ms.get_candles(body.instrument, timeframe=body.timeframe)
        candles = [_candle_to_dict(c) for c in raw_candles] if raw_candles else []

    if not candles:
        raise HTTPException(status_code=400, detail="No candle data available to compute indicator")

    options_ctx = await ResearchOptionsContext.get_context(body.instrument)
    current_price = float(candles[-1]["close"])

    context = IndicatorContext(
        instrument=body.instrument,
        timeframe=body.timeframe,
        timestamp=datetime.now(timezone.utc),
        candles=candles,
        current_price=current_price,
        options_context=options_ctx,
        parameters=body.parameters,
    )

    output = await ind.calculate(context)
    return output


# -------------------------------------------------------------
# 4. Predictions & Outcomes (§26, N5)
# -------------------------------------------------------------
@router.post("/predictions", response_model=Dict[str, str])
async def record_prediction(
    prediction: ResearchPrediction,
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Record an immutable research prediction.
    
    Rule N5: Once logged, prediction records are permanent and non-updatable.
    """
    pred_id = await PredictionService.record_prediction(prediction, session=session)
    return {"prediction_id": pred_id, "status": "RECORDED_IMMUTABLE"}


@router.get("/predictions", response_model=List[ResearchPrediction])
async def list_predictions(
    indicator_id: Optional[str] = Query(None),
    instrument: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """List recent predictions."""
    return await PredictionService.list_predictions(
        indicator_id=indicator_id,
        instrument=instrument,
        limit=limit,
        session=session,
    )


@router.get("/predictions/{prediction_id}", response_model=ResearchPrediction)
async def get_prediction(
    prediction_id: str,
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Get a prediction by ID."""
    pred = await PredictionService.get_prediction(prediction_id, session=session)
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")
    return pred


@router.get("/predictions/{prediction_id}/outcome", response_model=PredictionOutcome)
async def get_prediction_outcome(
    prediction_id: str,
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Get the recorded outcome for a prediction."""
    outcome = await PredictionService.get_outcome(prediction_id, session=session)
    if not outcome:
        raise HTTPException(status_code=404, detail="Outcome not yet evaluated or found")
    return outcome


@router.post("/predictions/{prediction_id}/measure", response_model=PredictionOutcome)
async def measure_prediction(
    prediction_id: str,
    body: MeasurePredictionRequest = Body(default=MeasurePredictionRequest()),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Evaluate and append forward outcome for an existing prediction."""
    pred = await PredictionService.get_prediction(prediction_id, session=session)
    if not pred:
        raise HTTPException(status_code=404, detail="Prediction not found")

    forward_candles = body.forward_candles
    if not forward_candles:
        # Fetch live candles from market service
        ms = MarketService()
        raw_candles = await ms.get_candles(pred.instrument, timeframe=pred.timeframe)
        forward_candles = [_candle_to_dict(c) for c in raw_candles[-pred.horizon_candles:]] if raw_candles else []

    if not forward_candles:
        raise HTTPException(status_code=400, detail="Insufficient forward candles to evaluate outcome")

    outcome = OutcomeMeasurer.evaluate_forward_candles(pred, forward_candles)
    await PredictionService.append_outcome(outcome, session=session)
    return outcome


# -------------------------------------------------------------
# 5. Offline Validation & Experiments (§19, §20)
# -------------------------------------------------------------
@router.post("/experiments/run")
async def run_experiment(
    req: RunExperimentRequest,
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Execute the Cheap Validation Gate for an indicator over historical candles."""
    ind = IndicatorRegistry.get(req.indicator_id)
    if not ind:
        raise HTTPException(status_code=404, detail=f"Indicator '{req.indicator_id}' not found")

    candles = req.candles
    if not candles:
        ms = MarketService()
        raw_candles = await ms.get_candles(req.instrument, timeframe=req.timeframe)
        candles = [_candle_to_dict(c) for c in raw_candles] if raw_candles else []

    if not candles or len(candles) < 35:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 35 candles to run backtest, got {len(candles)}",
        )

    options_ctx = await ResearchOptionsContext.get_context(req.instrument)
    run_record, report = await CheapValidationGate.run_experiment(
        indicator=ind,
        candles=candles,
        instrument=req.instrument,
        timeframe=req.timeframe,
        horizon_candles=req.horizon_candles,
        stride=req.stride,
        options_ctx=options_ctx,
        session=session,
    )

    return {
        "run": run_record,
        "report": report,
    }


# -------------------------------------------------------------
# 6. Snapshots (§25) & Annotations (§47)
# -------------------------------------------------------------
_memory_snapshots: Dict[str, ResearchSnapshot] = {}
_memory_annotations: Dict[str, ResearchAnnotation] = {}


@router.post("/snapshots", response_model=ResearchSnapshot)
async def create_snapshot(
    req: SnapshotCreateRequest,
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Save a market state snapshot."""
    snap_id = f"snap_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)
    snapshot = ResearchSnapshot(
        snapshot_id=snap_id,
        instrument=req.instrument,
        timeframe=req.timeframe,
        timestamp=now,
        price=req.price,
        regime=req.regime,
        session=req.session,
        features=req.features,
        options_context=req.options_context,
        data_quality=req.data_quality,
        created_at=now,
    )
    _memory_snapshots[snap_id] = snapshot

    if session is not None:
        try:
            import json
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
                    "id": snap_id,
                    "inst": req.instrument,
                    "tf": req.timeframe,
                    "ts": now,
                    "p": req.price,
                    "reg": req.regime,
                    "sess": req.session,
                    "feat": json.dumps(req.features),
                    "opt": json.dumps(req.options_context) if req.options_context else None,
                    "dq": req.data_quality.value if isinstance(req.data_quality, DataQualityStatus) else req.data_quality,
                    "created": now,
                }
            )
            await session.commit()
        except Exception as e:
            await session.rollback()
            logger.warning("save_snapshot_db_failed_memory_cached", error=str(e))

    return snapshot


@router.get("/snapshots", response_model=List[ResearchSnapshot])
async def list_snapshots(
    instrument: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List recent research snapshots."""
    snaps = list(_memory_snapshots.values())
    if instrument:
        snaps = [s for s in snaps if s.instrument == instrument]
    return sorted(snaps, key=lambda x: x.timestamp, reverse=True)[:limit]


@router.post("/annotations", response_model=ResearchAnnotation)
async def create_annotation(
    ann: ResearchAnnotation,
):
    """Record a chart annotation."""
    if not ann.annotation_id:
        ann.annotation_id = f"ann_{uuid.uuid4().hex[:12]}"
    if not ann.created_at:
        ann.created_at = datetime.now(timezone.utc)
    _memory_annotations[ann.annotation_id] = ann
    return ann


@router.get("/annotations", response_model=List[ResearchAnnotation])
async def list_annotations(
    instrument: Optional[str] = Query(None),
):
    """List chart annotations."""
    anns = list(_memory_annotations.values())
    if instrument:
        anns = [a for a in anns if a.instrument == instrument]
    return sorted(anns, key=lambda x: x.timestamp, reverse=True)
