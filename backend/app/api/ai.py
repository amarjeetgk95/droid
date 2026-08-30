from datetime import datetime, timezone
import time
import structlog
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from app.services.ai_service import ai_service
from app.services.openrouter_catalog import get_model_catalog, validate_model_or_raise, get_cache_status, clear_cache as clear_model_cache
from app.models.market import ApiMeta, DataStatus
from app.core.config import settings

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
# Compat alias for spec: GET /api/ai/models
compat_router = APIRouter(prefix="/api/ai", tags=["ai"])


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
    model: str | None = Query(default=None, description="OpenRouter model ID or auto (when provider=openrouter)"),
    allow_paid: bool | None = Query(default=None, description="Override free-only"),
):
    """Generate grounded, structured AI market analysis. Strict – fails if provider not configured (no silent mock)."""
    try:
        # If provider is openrouter and model specified, enforce free-only validation
        if provider.lower() == "openrouter" and model:
            # validate
            effective_free_only = not allow_paid if allow_paid is not None else getattr(settings, "openrouter_free_only", True)
            # This will raise if paid model requested while free-only
            await validate_model_or_raise(model, free_only=effective_free_only)
            insight = await ai_service.generate_market_analysis(symbol, provider, openrouter_model=model, allow_paid=allow_paid)
        else:
            insight = await ai_service.generate_market_analysis(symbol, provider)
        return {
            "data": insight.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except ValueError as e:
        msg = str(e)
        if "Paid models are disabled" in msg:
            raise HTTPException(status_code=403, detail=msg)
        # Configuration / connectivity errors → 400 with clear message
        raise HTTPException(status_code=400, detail=msg)
    except HTTPException:
        raise
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


# ---------------------------------------------------------------------------
# Dynamic OpenRouter Model Catalog
# ---------------------------------------------------------------------------

class AIModelAnalyzeRequest(BaseModel):
    model: str | None = None  # e.g. inclusionai/ling-3.0-flash-fin:free or auto
    provider: str | None = None
    symbol: str = "NIFTY"
    analysis_type: str | None = None  # multi_timeframe etc
    allow_paid: bool | None = None  # overrides free_only when explicitly enabled


async def _handle_models_list(
    free_only: bool | None = None,
    pricing: str | None = None,
    force_refresh: bool = False,
):
    try:
        # Default free_only from settings unless query overrides
        # pricing filter FREE/PAID/ALL
        pricing_filter = (pricing or "ALL").upper()
        if pricing_filter not in ("FREE", "PAID", "ALL"):
            pricing_filter = "ALL"

        # If free_only is None, use server default (true)
        catalog = await get_model_catalog(
            force_refresh=force_refresh,
            free_only=free_only,
            pricing_filter=pricing_filter,
        )
        # Build clean normalized response per spec, but preserve extra fields
        # Strip raw to keep payload light but keep if needed? spec says store both category and raw where practical
        # We will include minimal raw summary
        models_out = []
        for m in catalog["models"]:
            models_out.append({
                "id": m["id"],
                "name": m["name"],
                "is_free": m["is_free"],
                "context_length": m["context_length"],
                "input_price": m["input_price"],
                "output_price": m["output_price"],
                "pricing": m.get("pricing", {}),
                "supports_tools": m["supports_tools"],
                "supports_vision": m["supports_vision"],
                "description": m["description"],
                "category": m["category"],
                "trading_rank": m["trading_rank"],
                "recommended_for_trading": m["recommended_for_trading"],
                "badges": m.get("badges", []),
                "architecture": m.get("architecture"),
                "created": m.get("created"),
            })

        default_model = catalog.get("default_model")
        if default_model:
            default_out = {
                "id": default_model["id"],
                "name": default_model["name"],
                "is_free": default_model["is_free"],
                "category": default_model["category"],
                "trading_rank": default_model["trading_rank"],
                "recommended_for_trading": default_model["recommended_for_trading"],
            }
        else:
            default_out = None

        return {
            "provider": "openrouter",
            "updated_at": catalog["updated_at"],
            "free_only": catalog["free_only"],
            "pricing_filter": catalog.get("pricing_filter", "ALL"),
            "models": models_out,
            "default_model": default_out,
            "total_count": catalog["total_count"],
            "free_count": catalog["free_count"],
            "paid_count": catalog["paid_count"],
            "using_cached": catalog.get("using_cached", False),
            "cache_error": catalog.get("cache_error"),
            "cache_age_seconds": catalog.get("cache_age_seconds", 0),
        }
    except Exception as e:
        logger.warning("models_list_failed", error=str(e))
        raise HTTPException(status_code=502, detail=f"Failed to fetch OpenRouter catalog: {str(e)[:400]}")


@router.get("/models")
async def list_ai_models_v1(
    free_only: bool | None = Query(default=None, description="Filter to free models only"),
    pricing: str | None = Query(default=None, description="Pricing filter: FREE | PAID | ALL"),
    refresh: bool = Query(default=False, description="Force refresh from OpenRouter"),
):
    """Dynamic OpenRouter model catalog — free detection via pricing. Cached 5-15min."""
    data = await _handle_models_list(free_only=free_only, pricing=pricing, force_refresh=refresh)
    return {
        "data": data,
        "error": None if not data.get("cache_error") or data.get("using_cached") else data.get("cache_error"),
        "meta": _make_meta().model_dump(),
        "using_cached": data.get("using_cached"),
    }


@compat_router.get("/models")
async def list_ai_models_compat(
    free_only: bool | None = Query(default=None),
    pricing: str | None = Query(default=None),
    refresh: bool = Query(default=False),
):
    data = await _handle_models_list(free_only=free_only, pricing=pricing, force_refresh=refresh)
    return {
        "data": data,
        "error": None if not data.get("cache_error") or data.get("using_cached") else data.get("cache_error"),
        "meta": _make_meta().model_dump(),
        "using_cached": data.get("using_cached"),
    }


@router.post("/models/refresh")
async def refresh_ai_models():
    """Manual refresh trigger for UI."""
    data = await _handle_models_list(force_refresh=True)
    return {
        "data": data,
        "error": None,
        "meta": _make_meta().model_dump(),
        "using_cached": data.get("using_cached"),
    }


@compat_router.post("/models/refresh")
async def refresh_ai_models_compat():
    data = await _handle_models_list(force_refresh=True)
    return {
        "data": data,
        "error": None,
        "meta": _make_meta().model_dump(),
        "using_cached": data.get("using_cached"),
    }


@router.get("/models/cache-status")
async def models_cache_status():
    return {
        "data": get_cache_status(),
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.post("/analyze")
async def analyze_with_model(payload: AIModelAnalyzeRequest = Body(...)):
    """
    AI inference with dynamic model validation.
    Accepts selected model ID, validates against live catalog,
    enforces FREE-only protection.
    """
    start = time.perf_counter()
    symbol = (payload.symbol or "NIFTY").strip()
    model_id = (payload.model or payload.provider or "auto").strip()
    # Determine free_only: payload allow_paid overrides server default
    if payload.allow_paid is not None:
        free_only = not payload.allow_paid
    else:
        free_only = getattr(settings, "openrouter_free_only", True)
    # Support old provider param as alias
    provider = payload.provider or "openrouter"
    analysis_type = payload.analysis_type or "multi_timeframe"

    try:
        # Validate model against catalog
        validated = await validate_model_or_raise(model_id, free_only=free_only)
        effective_model = validated["id"]

        # Determine provider for ai_service
        # If model is openrouter model, provider is openrouter with specific model
        # Use openrouter provider
        # For backward compat, if provider is gemini/ollama, bypass catalog check and use that provider
        if provider.lower() in ("gemini", "ollama", "mock_ai", "mock"):
            # Those providers have their own validation; allow through
            insight = await ai_service.generate_market_analysis(symbol, provider_name=provider.lower())
        else:
            # Use openrouter with validated model
            insight = await ai_service.generate_market_analysis(
                symbol=symbol,
                provider_name="openrouter",
                openrouter_model=effective_model,
                allow_paid=not free_only,
            )

        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "ai_analyze_success",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_id=effective_model,
            analysis_type=analysis_type,
            symbol=symbol,
            latency_ms=latency_ms,
            success=True,
        )
        return {
            "data": insight.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
            "model_used": effective_model,
            "latency_ms": latency_ms,
        }
    except ValueError as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        msg = str(e)
        logger.warning(
            "ai_analyze_rejected",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_id=model_id,
            analysis_type=analysis_type,
            symbol=symbol,
            latency_ms=latency_ms,
            error=msg,
            success=False,
        )
        # Paid protection messages should be 403
        if "Paid models are disabled" in msg or "free model" in msg.lower():
            raise HTTPException(status_code=403, detail=msg)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    except Exception as e:
        latency_ms = int((time.perf_counter() - start) * 1000)
        logger.error(
            "ai_analyze_failed",
            timestamp=datetime.now(timezone.utc).isoformat(),
            model_id=model_id,
            analysis_type=analysis_type,
            symbol=symbol,
            latency_ms=latency_ms,
            error=str(e)[:400],
            success=False,
        )
        raise HTTPException(status_code=500, detail=str(e)[:500])


# Enhanced analyze/{symbol} with model validation
@router.post("/analyze/{symbol}/with-model")
async def analyze_symbol_with_model(
    symbol: str,
    model: str = Query(default="auto", description="OpenRouter model ID or auto"),
    allow_paid: bool | None = Query(default=None, description="Override free-only"),
):
    """Variant with model query param for chart integration."""
    return await analyze_with_model(
        AIModelAnalyzeRequest(model=model, symbol=symbol, allow_paid=allow_paid)
    )
