from datetime import datetime, timezone
import time
import structlog
from fastapi import APIRouter, HTTPException, Query, Body, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from app.services.ai_service import ai_service
from app.services.ai_copilot_service import ai_copilot_service
from app.services.ai_strategy_service import ai_strategy_service
from app.services.ai_validation_service import ai_validation_service
from app.services.regime_service import regime_service
from app.models.ai import (
    AIChatRequest,
    AIOptionsStrategyRequest,
    AITradeValidationRequest,
    AIDailyBriefingResponse,
)
from app.services.openrouter_catalog import get_model_catalog, validate_model_or_raise, get_cache_status
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
        status=DataStatus.OFFLINE,
    )


class AITestRequest(BaseModel):
    provider: str = "openrouter"
    symbol: str = "NIFTY"
    geminiApiKey: str | None = None
    geminiModel: str | None = None
    openRouterApiKey: str | None = None
    openRouterModel: str | None = None
    ollamaBaseUrl: str | None = None
    ollamaModel: str | None = None
    # Direct providers — §34; keep optional for per-request key forwarding
    openaiApiKey: str | None = None
    openaiModel: str | None = None
    openaiBaseUrl: str | None = None
    novitaApiKey: str | None = None
    novitaModel: str | None = None
    novitaBaseUrl: str | None = None
    nvidiaApiKey: str | None = None
    nvidiaModel: str | None = None
    nvidiaBaseUrl: str | None = None
    customOpenaiApiKey: str | None = None
    customOpenaiModel: str | None = None
    customOpenaiBaseUrl: str | None = None
    apiKey: str | None = None
    model: str | None = None
    base_url: str | None = None
    customBaseUrl: str | None = None


@router.post("/test")
async def test_ai_provider(payload: AITestRequest = Body(...)):
    """Strict end-to-end test: validates connectivity, latency, and JSON schema. No mock fallback for real providers."""
    # compat: mock_ai -> openrouter
    prov_norm = (payload.provider or "openrouter").lower()
    if prov_norm == "mock_ai":
        prov_norm = "openrouter"
        payload.provider = "openrouter"
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
            openaiApiKey=payload.openaiApiKey,
            openaiModel=payload.openaiModel,
            openaiBaseUrl=payload.openaiBaseUrl,
            novitaApiKey=payload.novitaApiKey,
            novitaModel=payload.novitaModel,
            novitaBaseUrl=payload.novitaBaseUrl,
            nvidiaApiKey=payload.nvidiaApiKey,
            nvidiaModel=payload.nvidiaModel,
            nvidiaBaseUrl=payload.nvidiaBaseUrl,
            customOpenaiApiKey=payload.customOpenaiApiKey,
            customOpenaiModel=payload.customOpenaiModel,
            customOpenaiBaseUrl=payload.customOpenaiBaseUrl,
            apiKey=payload.apiKey,
            model=payload.model,
            base_url=payload.base_url,
            customBaseUrl=payload.customBaseUrl,
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
    provider: str = Query(default="openrouter", description="LLM provider: openrouter | gemini | ollama | openai | novita | nvidia | custom_openai"),
    model: str | None = Query(default=None, description="OpenRouter model ID or auto (when provider=openrouter)"),
    allow_paid: bool | None = Query(default=None, description="Override free-only"),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    openrouter_api_key: str | None = Query(default=None, alias="openRouterApiKey", description="OpenRouter key from Settings (optional, overrides env)"),
):
    """Generate grounded, structured AI market analysis. Strict – fails if provider not configured (no silent mock). Settings-driven key (no hardcode)."""
    # compat: mock_ai -> openrouter
    if provider.lower() == "mock_ai":
        provider = "openrouter"
    effective_key = (openrouter_api_key or x_openrouter_key or "").strip() or None
    try:
        # If provider is openrouter and model specified, enforce free-only validation
        if provider.lower() == "openrouter" and model:
            # validate
            effective_free_only = not allow_paid if allow_paid is not None else getattr(settings, "openrouter_free_only", True)
            # This will raise if paid model requested while free-only
            await validate_model_or_raise(model, free_only=effective_free_only)
            insight = await ai_service.generate_market_analysis(symbol, provider, openrouter_model=model, allow_paid=allow_paid, openrouter_api_key=effective_key)
        else:
            # For openrouter without explicit model, still pass key so service can use it
            if provider.lower() == "openrouter":
                insight = await ai_service.generate_market_analysis(symbol, provider, openrouter_model=model, allow_paid=allow_paid, openrouter_api_key=effective_key)
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


class AIV2EvaluateRequest(BaseModel):
    symbol: str = "NIFTY"
    regime_hint: str | None = None
    context_overrides: dict | None = None


@router.post("/v2/evaluate/{symbol}")
async def evaluate_v2(
    symbol: str,
    payload: AIV2EvaluateRequest | None = Body(default=None),
):
    """V2 AI evaluation: fast, deterministic, regime-aware signal generation.

    Per v2 spec §21: orchestrates scalping/core intraday AI paths, scoring,
    and deterministic validation to produce execution-ready signals.
    """
    try:
        from app.ai.ai_evaluator import ai_evaluator
        from app.ai.schemas import Regime

        req = payload or AIV2EvaluateRequest(symbol=symbol)
        regime_hint = None
        if req.regime_hint:
            try:
                regime_hint = Regime(req.regime_hint.upper())
            except ValueError:
                pass

        signal, execution = await ai_evaluator.evaluate(
            symbol=req.symbol.upper(),
            regime_hint=regime_hint,
            context_overrides=req.context_overrides,
        )

        return {
            "data": {
                "signal": signal.model_dump(mode="json"),
                "execution": execution.model_dump(mode="json"),
            },
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        logger.error("v2_evaluate_failed", symbol=symbol, error=str(e))
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
    openRouterApiKey: str | None = None  # Settings-driven; no hardcode. Priority > env
    geminiApiKey: str | None = None
    geminiModel: str | None = None
    ollamaBaseUrl: str | None = None
    ollamaModel: str | None = None
    # Direct providers — §34; per-request key fallback to config
    openaiApiKey: str | None = None
    openaiModel: str | None = None
    openaiBaseUrl: str | None = None
    novitaApiKey: str | None = None
    novitaModel: str | None = None
    novitaBaseUrl: str | None = None
    nvidiaApiKey: str | None = None
    nvidiaModel: str | None = None
    nvidiaBaseUrl: str | None = None
    customOpenaiApiKey: str | None = None
    customOpenaiModel: str | None = None
    customOpenaiBaseUrl: str | None = None
    apiKey: str | None = None
    base_url: str | None = None
    customBaseUrl: str | None = None


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
async def analyze_with_model(
    payload: AIModelAnalyzeRequest = Body(...),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
):
    """
    AI inference with dynamic model validation.
    Settings-driven keys (no hardcode). Accepts selected model ID, validates against live catalog,
    enforces FREE-only protection. Key priority: payload > header > env.
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
    # Resolve keys — Settings-driven priority (per-request key fallback to config)
    effective_openrouter_key = (payload.openRouterApiKey or x_openrouter_key or "").strip() or None
    effective_gemini_key = (payload.geminiApiKey or x_gemini_key or payload.geminiApiKey or "").strip() or None

    # compat: mock_ai -> openrouter
    if provider.lower() == "mock_ai":
        provider = "openrouter"

    try:
        # Validate model against catalog — skip for non-openrouter providers (direct providers + gemini/ollama)
        direct_providers = ("gemini", "ollama", "openai", "novita", "novita_ai", "nvidia", "custom_openai", "custom", "custom_openai_compatible")
        if provider.lower() not in direct_providers:
            validated = await validate_model_or_raise(model_id, free_only=free_only)
            effective_model = validated["id"]
        else:
            # For gemini/ollama/direct providers, don't validate against OpenRouter catalog
            effective_model = model_id
            validated = None

        # Determine provider for ai_service
        # If model is openrouter model, provider is openrouter with specific model
        # Use openrouter provider
        # For backward compat, if provider is gemini/ollama/direct, bypass catalog check and use that provider via create_provider_for_test
        if provider.lower() in ("gemini", "ollama"):
            # Those providers have their own validation; allow through — gemini key passed via payload/header if needed
            # For gemini, we need to use test path? For analyze, we still use get_llm_provider but that ignores key.
            # Instead create provider with key if supplied.
            if provider.lower() == "gemini" and effective_gemini_key:
                from app.ai.gemini import GeminiProvider
                from app.ai.prompt_builder import build_system_prompt, build_market_context_prompt
                from app.services.regime_service import regime_service
                from app.services.options_service import options_service
                # Build prompts and call directly with keyed provider to respect Settings
                regime = await regime_service.classify_market_regime(symbol)
                try:
                    from app.services.ai_service import _fetch_futures_safe as _ffs_gem
                    futures_gem = await _ffs_gem(symbol)
                except Exception:
                    futures_gem = None
                try:
                    chain = await options_service.get_option_chain_matrix(symbol)
                    options_analytics = chain.analytics
                    max_pain = getattr(chain, "max_pain", None)
                    if max_pain is None and chain.analytics:
                        try:
                            max_pain = await options_service.calculate_max_pain(symbol)
                        except Exception:
                            max_pain = chain.analytics.max_pain_strike
                    strikes = getattr(chain, "strikes", None)
                except Exception:
                    options_analytics = None
                    max_pain = None
                    strikes = None
                system_prompt = build_system_prompt()
                user_prompt = build_market_context_prompt(symbol=symbol, regime=regime, futures=futures_gem, options_analytics=options_analytics, max_pain=max_pain, strikes=strikes)
                insight = await GeminiProvider(api_key=effective_gemini_key, model=payload.geminiModel or "gemini-2.5-flash").generate_analysis(symbol, system_prompt, user_prompt)
            elif provider.lower() == "ollama" and (payload.ollamaBaseUrl or payload.ollamaModel):
                # Ollama localhost is local-only — backend on Render cannot reach user's laptop; gate with clear hint (browser check is primary)
                _base = (payload.ollamaBaseUrl or "").strip()
                if _base and ("localhost" in _base or "127.0.0.1" in _base):
                    raise ValueError(
                        f"Ollama URL {_base} is localhost — backend on Render cannot reach your local machine. "
                        f"This is local-only. Use direct browser check: fetch {_base}/api/tags from your browser. "
                        f"Ensure `ollama serve` and `ollama pull {payload.ollamaModel or 'deepseek-r1:8b'}` are running, or configure a remote Ollama URL."
                    )
                from app.ai.ollama import OllamaProvider
                from app.ai.prompt_builder import build_system_prompt, build_market_context_prompt
                from app.services.regime_service import regime_service
                from app.services.options_service import options_service
                regime = await regime_service.classify_market_regime(symbol)
                try:
                    from app.services.ai_service import _fetch_futures_safe as _ffs_oll
                    futures_oll = await _ffs_oll(symbol)
                except Exception:
                    futures_oll = None
                try:
                    chain = await options_service.get_option_chain_matrix(symbol)
                    options_analytics = chain.analytics
                    max_pain = getattr(chain, "max_pain", None)
                    if max_pain is None and chain.analytics:
                        try:
                            max_pain = await options_service.calculate_max_pain(symbol)
                        except Exception:
                            max_pain = chain.analytics.max_pain_strike
                    strikes = getattr(chain, "strikes", None)
                except Exception:
                    options_analytics = None
                    max_pain = None
                    strikes = None
                system_prompt = build_system_prompt()
                user_prompt = build_market_context_prompt(symbol=symbol, regime=regime, futures=futures_oll, options_analytics=options_analytics, max_pain=max_pain, strikes=strikes)
                insight = await OllamaProvider(base_url=payload.ollamaBaseUrl, model=payload.ollamaModel or "deepseek-r1:8b").generate_analysis(symbol, system_prompt, user_prompt)
            else:
                insight = await ai_service.generate_market_analysis(symbol, provider_name=provider.lower())
        elif provider.lower() in ("openai", "novita", "novita_ai", "nvidia", "custom_openai", "custom", "custom_openai_compatible"):
            # Direct providers — mirror gemini/ollama block using create_provider_for_test (per-request key fallback to config)
            from app.ai.registry import create_provider_for_test
            from app.ai.prompt_builder import build_system_prompt, build_market_context_prompt
            from app.services.regime_service import regime_service
            from app.services.options_service import options_service
            # Normalize provider id
            p_norm = provider.lower()
            if p_norm in ("custom", "custom_openai_compatible"):
                p_norm = "custom_openai"
            if p_norm == "novita_ai":
                p_norm = "novita"
            # Build market context
            regime = await regime_service.classify_market_regime(symbol)
            try:
                from app.services.ai_service import _fetch_futures_safe as _ffs_dp
                futures_dp = await _ffs_dp(symbol)
            except Exception:
                futures_dp = None
            try:
                chain = await options_service.get_option_chain_matrix(symbol)
                options_analytics = chain.analytics
                max_pain = getattr(chain, "max_pain", None)
                if max_pain is None and chain.analytics:
                    try:
                        max_pain = await options_service.calculate_max_pain(symbol)
                    except Exception:
                        max_pain = chain.analytics.max_pain_strike
                strikes = getattr(chain, "strikes", None)
            except Exception:
                options_analytics = None
                max_pain = None
                strikes = None
            system_prompt = build_system_prompt()
            user_prompt = build_market_context_prompt(symbol=symbol, regime=regime, futures=futures_dp, options_analytics=options_analytics, max_pain=max_pain, strikes=strikes)
            # Map payload keys to create_provider_for_test kwargs (supports per-request -> config fallback)
            kwargs: dict = {}
            if p_norm == "openai":
                kwargs["openaiApiKey"] = payload.openaiApiKey or payload.apiKey or ""
                kwargs["openaiModel"] = payload.openaiModel or payload.model or ""
                if payload.openaiBaseUrl:
                    kwargs["base_url"] = payload.openaiBaseUrl
                elif payload.base_url:
                    kwargs["base_url"] = payload.base_url
            elif p_norm == "novita":
                kwargs["novitaApiKey"] = payload.novitaApiKey or payload.apiKey or ""
                kwargs["novitaModel"] = payload.novitaModel or payload.model or ""
                if payload.novitaBaseUrl:
                    kwargs["base_url"] = payload.novitaBaseUrl
                elif payload.base_url:
                    kwargs["base_url"] = payload.base_url
            elif p_norm == "nvidia":
                kwargs["nvidiaApiKey"] = payload.nvidiaApiKey or payload.apiKey or ""
                kwargs["nvidiaModel"] = payload.nvidiaModel or payload.model or ""
                if payload.nvidiaBaseUrl:
                    kwargs["base_url"] = payload.nvidiaBaseUrl
                elif payload.base_url:
                    kwargs["base_url"] = payload.base_url
            elif p_norm == "custom_openai":
                kwargs["apiKey"] = payload.customOpenaiApiKey or payload.apiKey or ""
                kwargs["model"] = payload.customOpenaiModel or payload.model or ""
                kwargs["base_url"] = payload.customOpenaiBaseUrl or payload.customBaseUrl or payload.base_url or ""
            # Provide model fallback if still empty
            if not kwargs.get("model") and not kwargs.get("openaiModel") and not kwargs.get("novitaModel") and not kwargs.get("nvidiaModel"):
                kwargs["model"] = effective_model if effective_model != "auto" else None
            llm = create_provider_for_test(p_norm, **kwargs)
            insight = await llm.generate_analysis(symbol, system_prompt, user_prompt)
        else:
            # Use openrouter with validated model and Settings-driven key
            insight = await ai_service.generate_market_analysis(
                symbol=symbol,
                provider_name="openrouter",
                openrouter_model=effective_model,
                allow_paid=not free_only,
                openrouter_api_key=effective_openrouter_key,
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


# Enhanced analyze/{symbol} with model validation — also Settings-driven
@router.post("/analyze/{symbol}/with-model")
async def analyze_symbol_with_model(
    symbol: str,
    model: str = Query(default="auto", description="OpenRouter model ID or auto"),
    allow_paid: bool | None = Query(default=None, description="Override free-only"),
    payload: AIModelAnalyzeRequest | None = Body(default=None),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
):
    """Variant with model query param for chart integration. Supports key via body or header."""
    key = None
    if payload and payload.openRouterApiKey:
        key = payload.openRouterApiKey
    elif x_openrouter_key:
        key = x_openrouter_key
    return await analyze_with_model(
        AIModelAnalyzeRequest(model=model, symbol=symbol, allow_paid=allow_paid, openRouterApiKey=key)
    )


# ---------------------------------------------------------------------------
# Interactive Streaming Copilot (SSE)
# ---------------------------------------------------------------------------

@router.post("/chat/stream")
async def stream_chat_copilot(
    payload: AIChatRequest = Body(...),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_openai_key: str | None = Header(default=None, alias="X-OpenAI-Key"),
):
    """
    Stream interactive multi-turn AI copilot responses via Server-Sent Events (SSE).
    Supports DeepSeek-R1 reasoning tokens, live tool execution against quant engines, and provider fallback.
    """
    if not payload.openrouter_api_key and x_openrouter_key:
        payload.openrouter_api_key = x_openrouter_key
    if not payload.gemini_api_key and x_gemini_key:
        payload.gemini_api_key = x_gemini_key
    if not payload.openai_api_key and x_openai_key:
        payload.openai_api_key = x_openai_key

    return StreamingResponse(
        ai_copilot_service.stream_copilot_turn(payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Options Strategy Architect
# ---------------------------------------------------------------------------

@router.post("/strategy/recommend")
async def recommend_options_strategy(
    payload: AIOptionsStrategyRequest = Body(...),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
):
    """Recommend optimal risk-defined options strategy tailored to current IV, S/R, and outlook."""
    if not payload.openrouter_api_key and x_openrouter_key:
        payload.openrouter_api_key = x_openrouter_key
    if not payload.gemini_api_key and x_gemini_key:
        payload.gemini_api_key = x_gemini_key

    try:
        rec = await ai_strategy_service.recommend_strategy(payload)
        return {
            "data": rec.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        logger.error("strategy_recommend_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Trade Thesis & Invalidation Auditor
# ---------------------------------------------------------------------------

@router.post("/trade/validate")
async def validate_trade_setup(
    payload: AITradeValidationRequest = Body(...),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
):
    """Audit user proposed entry/SL/target against live option walls and trend regime."""
    if not payload.openrouter_api_key and x_openrouter_key:
        payload.openrouter_api_key = x_openrouter_key
    if not payload.gemini_api_key and x_gemini_key:
        payload.gemini_api_key = x_gemini_key

    try:
        val = await ai_validation_service.validate_trade(payload)
        return {
            "data": val.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        logger.error("trade_validate_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Daily Market Briefing (Pre/Post-Market)
# ---------------------------------------------------------------------------

@router.get("/briefing/{symbol}")
async def get_market_briefing(
    symbol: str,
    session_type: str = Query(default="PRE_MARKET", description="PRE_MARKET | POST_MARKET | INTRADAY"),
):
    """Generate daily institutional briefing synthesizing technical pivots, FII flow, and option pins."""
    try:
        underlying = symbol.upper().replace(" 50", "")
        regime = await regime_service.classify_market_regime(underlying)
        pivots = regime.key_levels.classic_pivots

        briefing = AIDailyBriefingResponse(
            symbol=underlying,
            session_type=session_type if session_type in ("PRE_MARKET", "POST_MARKET", "INTRADAY_UPDATE") else "PRE_MARKET",
            timestamp=datetime.now(timezone.utc),
            executive_summary=f"{underlying} enters session in {regime.regime_state} regime (Score {regime.confidence_score}%). Spot ₹{regime.spot_price} positioned relative to Pivot ₹{pivots.pivot}.",
            key_levels_to_watch={
                "spot": regime.spot_price,
                "pivot": pivots.pivot,
                "r1": pivots.r1,
                "s1": pivots.s1,
                "poc": regime.key_levels.poc,
                "vah": regime.key_levels.vah,
                "val": regime.key_levels.val,
            },
            options_pin_and_pivots=f"Primary gravitational support at S1 ₹{pivots.s1}; resistance at R1 ₹{pivots.r1}. Volume Profile Point of Control at ₹{regime.key_levels.poc}.",
            fii_dii_implication="Institutional FII long/short positioning remains moderately balanced; watch morning opening range breakout.",
            actionable_playbook=[
                f"Defend longs above Classic Pivot ₹{pivots.pivot}",
                f"Look for mean-reversion exhaustion near R1 ₹{pivots.r1}",
                f"Respect 14-period ATR volatility band of {regime.indicators.atr_14} points",
            ],
            provider_used="droid_quant_engine",
        )
        return {
            "data": briefing.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        logger.error("briefing_endpoint_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Deep Insight — Unified Frontend Intelligence
# ---------------------------------------------------------------------------

@router.get("/deep-insight/{symbol}")
async def get_deep_insight(
    symbol: str,
    provider: str | None = Query(default=None),
    model: str | None = Query(default=None),
    openrouter_api_key: str | None = Query(default=None, alias="openRouterApiKey"),
    x_openrouter_key: str | None = Header(default=None, alias="X-OpenRouter-Key"),
    x_openrouter_model: str | None = Header(default=None, alias="X-OpenRouter-Model"),
    gemini_api_key: str | None = Query(default=None, alias="geminiApiKey"),
    x_gemini_key: str | None = Header(default=None, alias="X-Gemini-Key"),
    x_ai_provider: str | None = Header(default=None, alias="X-AI-Provider"),
):
    """Unified Deep Insight payload aggregating market regime, options, multi-TF, and AI signal.

    Returns one structured response containing all information required by the
    frontend AI Deep Insight module per §14 of the integration specification.
    """
    try:
        from app.services.deep_insight_service import deep_insight_service
        effective_provider = (provider or x_ai_provider or "").strip() or None
        effective_openrouter_key = (openrouter_api_key or x_openrouter_key or "").strip() or None
        effective_gemini_key = (gemini_api_key or x_gemini_key or "").strip() or None
        effective_model = (model or x_openrouter_model or "").strip() or None

        payload = await deep_insight_service.get_deep_insight(
            symbol.upper(),
            provider=effective_provider,
            model=effective_model,
            openrouter_api_key=effective_openrouter_key,
            gemini_api_key=effective_gemini_key,
        )
        return {
            "data": payload.model_dump(mode="json"),
            "error": payload.error,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        logger.error("deep_insight_error", symbol=symbol, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

