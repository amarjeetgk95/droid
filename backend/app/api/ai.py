from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from app.services.ai_service import ai_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="ai_insights_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


class AITestRequest(BaseModel):
    provider: str = "mock_ai"
    symbol: str = "NIFTY"
    geminiApiKey: str | None = None
    geminiModel: str | None = None
    openRouterApiKey: str | None = None
    openRouterModel: str | None = None
    ollamaBaseUrl: str | None = None
    ollamaModel: str | None = None


@router.post("/test")
async def test_ai_provider(payload: AITestRequest = Body(...)):
    """Strict end-to-end test: validates connectivity, latency, and JSON schema. No mock fallback for real providers."""
    try:
        result = await ai_service.test_provider(
            symbol=payload.symbol,
            provider=payload.provider,
            geminiApiKey=payload.geminiApiKey,
            geminiModel=payload.geminiModel,
            openRouterApiKey=payload.openRouterApiKey,
            openRouterModel=payload.openRouterModel,
            ollamaBaseUrl=payload.ollamaBaseUrl,
            ollamaModel=payload.ollamaModel,
        )
        # Always return 200 with success flag, so frontend can show detailed diagnostics
        return {
            "data": result,
            "error": None if result.get("success") else result.get("error"),
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze/{symbol}")
async def generate_market_analysis(
    symbol: str,
    provider: str = Query(default="mock_ai", description="LLM provider: mock_ai | gemini | openrouter | ollama"),
):
    """Generate grounded, structured AI market analysis. Strict – fails if provider not configured (no silent mock)."""
    try:
        insight = await ai_service.generate_market_analysis(symbol, provider)
        return {
            "data": insight.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except ValueError as e:
        # Configuration / connectivity errors → 400 with clear message
        raise HTTPException(status_code=400, detail=str(e))
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
