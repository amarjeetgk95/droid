from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from app.services.ai_service import ai_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="ai_insights_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.post("/analyze/{symbol}")
async def generate_market_analysis(
    symbol: str,
    provider: str = Query(default="mock_ai", description="LLM provider: mock_ai | gemini"),
):
    """Generate grounded, structured AI market analysis across Options, Futures, and Technicals."""
    try:
        insight = await ai_service.generate_market_analysis(symbol, provider)
        return {
            "data": insight.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{symbol}")
async def get_analysis_history(symbol: str):
    """Retrieve historical market intelligence reports for a symbol."""
    try:
        history = await ai_service.get_history_async(symbol)
        return {
            "data": [h.model_dump(mode="json") for h in history],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
