import uuid
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.models.ai import AIInsightResponse, AIHistoryItem
from app.services.regime_service import regime_service
from app.services.options_service import options_service
from app.ai.prompt_builder import build_system_prompt, build_market_context_prompt
from app.ai.registry import get_llm_provider, create_provider_for_test
from app.core.database import get_async_session_factory
from app.repositories.ai_repository import AIRepository
import structlog

logger = structlog.get_logger()


class AIService:
    """Multi-Phase Intelligence Aggregation & AI Market Analyst Service."""

    def __init__(self):
        self._history: dict[str, list[AIHistoryItem]] = {}

    async def generate_market_analysis(
        self,
        symbol: str = "NIFTY",
        provider_name: str = "openrouter",
        user_id: Optional[UUID] = None,
        openrouter_model: str | None = None,
        allow_paid: bool | None = None,
        analysis_type: str | None = None,
        openrouter_api_key: str | None = None,
    ) -> AIInsightResponse:
        """Aggregate cross-phase metrics and generate structured AI report."""
        underlying = symbol.upper().replace(" 50", "")

        # 1. Fetch Regime & Key Levels (Phase 6)
        regime = await regime_service.classify_market_regime(underlying)

        # 2. Fetch Options & Max Pain (Phase 4) — also retain strike rows for §8 detailed checklist (Key Strikes, Premiums, Greeks)
        options_analytics = None
        max_pain = None
        strikes = None
        try:
            chain = await options_service.get_option_chain_matrix(underlying)
            options_analytics = chain.analytics
            # chain has no direct .max_pain field; derive robustly (analytics fallback or calculated MaxPainResult)
            max_pain = getattr(chain, "max_pain", None)
            if max_pain is None and chain.analytics:
                # fallback to max_pain strike value; calculate full result if needed
                try:
                    max_pain = await options_service.calculate_max_pain(underlying)
                except Exception:
                    max_pain = chain.analytics.max_pain_strike
            strikes = getattr(chain, "strikes", None)
        except Exception as e:
            logger.warning("options_data_fetch_warn", symbol=underlying, error=str(e))

        # 4. Construct Grounded Prompts ( §8 exhaustive F&O + §22 ingestion guardrails )
        system_prompt = build_system_prompt()
        user_prompt = build_market_context_prompt(
            symbol=underlying,
            regime=regime,
            options_analytics=options_analytics,
            max_pain=max_pain,
            strikes=strikes,
        )

        # 5. Dispatch to LLM Provider (strict – no silent mock fallback)
        # Handle openrouter – Settings-driven (no hardcode). Supports per-request key from UI.
        if provider_name.lower() == "openrouter":
            # Validate against catalog before inference (hard protection)
            from app.services.openrouter_catalog import validate_model_or_raise
            from app.core.config import settings as cfg
            # Determine effective free_only
            effective_allow_paid = allow_paid
            if effective_allow_paid is None:
                # use server default free_only
                effective_free_only = getattr(cfg, "openrouter_free_only", True)
                effective_allow_paid = not effective_free_only
            else:
                effective_free_only = not effective_allow_paid

            # Validate (also handles auto resolution) — default to auto if no model supplied
            model_to_validate = (openrouter_model or "auto").strip()
            if model_to_validate.lower() in ("auto", "auto — best free for trading", ""):
                validated = await validate_model_or_raise("auto", free_only=effective_free_only)
                effective_model = validated["id"]
            else:
                validated = await validate_model_or_raise(model_to_validate, free_only=effective_free_only)
                effective_model = validated["id"]

            # Log inference attempt (no api key)
            logger.info(
                "ai_inference_attempt",
                timestamp=datetime.now(timezone.utc).isoformat(),
                model_id=effective_model,
                analysis_type=analysis_type or "multi_timeframe",
                symbol=underlying,
                free_only=effective_free_only,
            )

            # Create provider — Settings-driven key (no hardcode). Priority: request key > env fallback
            from app.ai.openrouter import OpenRouterProvider
            from app.core.config import settings as cfg2
            # Priority: per-request key (from Settings UI) > server env
            api_key = (openrouter_api_key or "").strip()
            if not api_key:
                api_key = (getattr(cfg2, "openrouter_api_key", "") or getattr(cfg2, "OPENROUTER_API_KEY", "") or "").strip()
            provider = OpenRouterProvider(api_key=api_key, model=effective_model)
            # Record token usage timing
            t0 = time.perf_counter()
            try:
                insight = await provider.generate_analysis(underlying, system_prompt, user_prompt)
                latency_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(
                    "ai_inference_success",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    model_id=effective_model,
                    analysis_type=analysis_type or "multi_timeframe",
                    symbol=underlying,
                    latency_ms=latency_ms,
                    success=True,
                )
            except Exception as e:
                latency_ms = int((time.perf_counter() - t0) * 1000)
                logger.warning(
                    "ai_inference_failed",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    model_id=effective_model,
                    analysis_type=analysis_type or "multi_timeframe",
                    symbol=underlying,
                    latency_ms=latency_ms,
                    error=str(e)[:400],
                    success=False,
                )
                raise
        else:
            provider = get_llm_provider(provider_name)
            insight = await provider.generate_analysis(underlying, system_prompt, user_prompt)

        # 6. Save to In-Memory Cache
        if underlying not in self._history:
            self._history[underlying] = []

        history_entry = AIHistoryItem(
            id=str(uuid.uuid4())[:8],
            symbol=underlying,
            timestamp=insight.timestamp,
            market_bias=insight.market_bias,
            confidence=insight.confidence,
            executive_summary=insight.executive_summary,
        )
        self._history[underlying].insert(0, history_entry)
        self._history[underlying] = self._history[underlying][:20]

        # 7. Persist to Supabase PostgreSQL
        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    await AIRepository.save_report(session, insight, user_id=user_id)
            except Exception as e:
                logger.warning("failed_to_save_ai_report_supabase", error=str(e))

        return insight

    async def get_history_async(self, symbol: str = "NIFTY", limit: int = 20) -> list[AIHistoryItem]:
        """Retrieve recent market intelligence reports from Supabase with memory fallback."""
        underlying = symbol.upper().replace(" 50", "")
        factory = get_async_session_factory()
        if factory:
            try:
                async with factory() as session:
                    db_history = await AIRepository.get_history(session, underlying, limit=limit)
                    if db_history:
                        return db_history
            except Exception as e:
                logger.warning("failed_to_fetch_ai_history_supabase", error=str(e))

        return self._history.get(underlying, [])

    def get_history(self, symbol: str = "NIFTY") -> list[AIHistoryItem]:
        """Sync retrieve method for backwards compatibility."""
        underlying = symbol.upper().replace(" 50", "")
        return self._history.get(underlying, [])

    async def test_provider(
        self,
        symbol: str = "NIFTY",
        provider: str = "openrouter",
        geminiApiKey: str | None = None,
        geminiModel: str | None = None,
        openRouterApiKey: str | None = None,
        openRouterModel: str | None = None,
        ollamaBaseUrl: str | None = None,
        ollamaModel: str | None = None,
    ) -> dict:
        """Strict connectivity + prompt + schema test. Returns latency and detailed result."""
        # Real providers – instantiate with supplied keys and do strict test
        underlying = symbol.upper().replace(" 50", "")
        regime = await regime_service.classify_market_regime(underlying)
        strikes = None
        try:
            chain = await options_service.get_option_chain_matrix(underlying)
            options_analytics = chain.analytics
            max_pain = getattr(chain, "max_pain", None)
            if max_pain is None and chain.analytics:
                try:
                    max_pain = await options_service.calculate_max_pain(underlying)
                except Exception:
                    max_pain = chain.analytics.max_pain_strike
            strikes = getattr(chain, "strikes", None)
        except Exception:
            options_analytics = None
            max_pain = None
            strikes = None
        system_prompt = build_system_prompt()
        user_prompt = build_market_context_prompt(symbol=underlying, regime=regime, options_analytics=options_analytics, max_pain=max_pain, strikes=strikes)

        # Special handling for Ollama when base_url is localhost – backend on Render cannot reach user's laptop.
        # We still try, but will return a clear error indicating frontend must test Ollama directly.
        if provider.lower() == "ollama" and ollamaBaseUrl and ("localhost" in ollamaBaseUrl or "127.0.0.1" in ollamaBaseUrl):
            return {
                "success": False,
                "provider": "ollama",
                "model": ollamaModel or "deepseek-r1:8b",
                "latency_ms": 0,
                "schema_valid": False,
                "is_mock": False,
                "error": f"Ollama URL {ollamaBaseUrl} is localhost. Backend (Render) cannot reach your local machine. Test Ollama directly from your browser – the UI will attempt a direct fetch to {ollamaBaseUrl}/api/tags. If that fails, start Ollama with `ollama serve` and `ollama pull {ollamaModel or 'deepseek-r1:8b'}`.",
                "hint": "Frontend will run a direct browser check to your Ollama instance. Ensure Ollama is running and CORS is allowed, or use a remote Ollama URL.",
            }

        # Strict OpenRouter validation: enforce FREE-only and resolve `auto` before provider instantiation
        # This prevents paid model leakage and ensures test uses real catalog (no mock fallback)
        effective_openrouter_model = openRouterModel
        if provider.lower() == "openrouter":
            from app.services.openrouter_catalog import validate_model_or_raise
            from app.core.config import settings as _cfg
            # Derive free_only from server setting (single source of truth for strict mode)
            effective_free_only = getattr(_cfg, "openrouter_free_only", True)
            # Resolve model_id: 'auto' or None -> best free; otherwise validate supplied id
            raw_model = (openRouterModel or "auto").strip()
            if raw_model.lower() in ("auto", "auto — best free for trading", "auto-best-free-for-trading", ""):
                raw_model = "auto"
            try:
                validated = await validate_model_or_raise(raw_model, free_only=effective_free_only)
                effective_openrouter_model = validated["id"]
            except ValueError as ve:
                # Honest failure – includes pricing guard message
                return {
                    "success": False,
                    "provider": "openrouter",
                    "model": raw_model,
                    "latency_ms": 0,
                    "schema_valid": False,
                    "is_mock": False,
                    "error": str(ve),
                    "hint": "Select a FREE OpenRouter model (prompt=0 & completion=0). Try Auto — Best Free, or refresh the model catalog.",
                }
            except Exception as e:
                return {
                    "success": False,
                    "provider": "openrouter",
                    "model": raw_model,
                    "latency_ms": 0,
                    "schema_valid": False,
                    "is_mock": False,
                    "error": f"OpenRouter catalog validation failed: {str(e)[:400]}",
                    "hint": "Catalog may be temporarily unavailable. Retry with Refresh Models.",
                }

        llm = create_provider_for_test(
            provider,
            geminiApiKey=geminiApiKey,
            geminiModel=geminiModel,
            openRouterApiKey=openRouterApiKey,
            openRouterModel=effective_openrouter_model,
            ollamaBaseUrl=ollamaBaseUrl,
            ollamaModel=ollamaModel,
        )
        start = time.perf_counter()
        try:
            insight = await llm.generate_analysis(underlying, system_prompt, user_prompt)
            latency_ms = int((time.perf_counter() - start) * 1000)
            # Schema already validated by Pydantic; if we got here, it's valid
            return {
                "success": True,
                "provider": provider,
                "model": getattr(llm, "model", provider),
                "latency_ms": latency_ms,
                "schema_valid": True,
                "is_mock": False,
                "message": f"Successfully generated structured market intelligence via {provider} in {latency_ms}ms. Schema validation passed.",
                "insight": insight.model_dump(mode="json"),
            }
        except Exception as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            msg = str(e)
            return {
                "success": False,
                "provider": provider,
                "model": getattr(llm, "model", provider),
                "latency_ms": latency_ms,
                "schema_valid": False,
                "is_mock": False,
                "error": msg,
                "hint": "Check API key, model name, and network. For Ollama, ensure `ollama serve` is running.",
            }


ai_service = AIService()
