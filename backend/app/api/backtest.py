from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException
from app.services.backtest_service import backtest_service
from app.models.backtest import BacktestPayload
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="backtesting_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.post("/run")
async def run_backtest_simulation(payload: BacktestPayload):
    """Execute quantitative strategy backtest simulation."""
    try:
        result = backtest_service.execute_backtest(payload)
        return {
            "data": result.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/presets")
async def get_backtest_presets():
    """Retrieve pre-configured strategy templates."""
    try:
        presets = backtest_service.get_presets()
        return {
            "data": [p.model_dump(mode="json") for p in presets],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_backtest_history():
    """Retrieve recent backtest run results."""
    try:
        history = backtest_service.get_history()
        return {
            "data": [h.model_dump(mode="json") for h in history],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
