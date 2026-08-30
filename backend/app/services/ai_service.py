import uuid
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.models.ai import AIInsightResponse, AIHistoryItem
from app.services.regime_service import regime_service
from app.services.futures_service import futures_service
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
        provider_name: str = "mock_ai",
        user_id: Optional[UUID] = None,
    ) -> AIInsightResponse:
        """Aggregate cross-phase metrics and generate structured AI report."""
        underlying = symbol.upper().replace(" 50", "")

        # 1. Fetch Regime & Key Levels (Phase 6)
        regime = await regime_service.classify_market_regime(underlying)

        # 2. Fetch Futures & Rollover (Phase 5)
        futures = await futures_service.get_futures_overview(underlying)

        # 3. Fetch Options & Max Pain (Phase 4)
        options_analytics = None
        max_pain = None
        try:
            chain = await options_service.get_option_chain_matrix(underlying)
            options_analytics = chain.analytics
            max_pain = chain.max_pain
        except Exception as e:
            logger.warning("options_data_fetch_warn", symbol=underlying, error=str(e))

        # 4. Construct Grounded Prompts
        system_prompt = build_system_prompt()
        user_prompt = build_market_context_prompt(
            symbol=underlying,
            regime=regime,
            futures=futures,
            options_analytics=options_analytics,
            max_pain=max_pain,
        )

        # 5. Dispatch to LLM Provider (strict – no silent mock fallback)
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
        provider: str = "mock_ai",
        geminiApiKey: str | None = None,
        geminiModel: str | None = None,
        openRouterApiKey: str | None = None,
        openRouterModel: str | None = None,
        ollamaBaseUrl: str | None = None,
        ollamaModel: str | None = None,
    ) -> dict:
        """Strict connectivity + prompt + schema test. Returns latency and detailed result, never falls back to mock."""
        # For mock_ai we just validate prompt building and mock generation (honest: it's mock)
        if provider.lower() in ("mock_ai", "mock"):
            start = time.perf_counter()
            # Still do real prompt building to verify pipeline
            underlying = symbol.upper().replace(" 50", "")
            regime = await regime_service.classify_market_regime(underlying)
            futures = await futures_service.get_futures_overview(underlying)
            try:
                chain = await options_service.get_option_chain_matrix(underlying)
                options_analytics = chain.analytics
                max_pain = chain.max_pain
            except Exception:
                options_analytics = None
                max_pain = None
            system_prompt = build_system_prompt()
            user_prompt = build_market_context_prompt(symbol=underlying, regime=regime, futures=futures, options_analytics=options_analytics, max_pain=max_pain)
            # Mock generate (honest mock)
            from app.ai.mock_ai import MockLLMProvider
            insight = await MockLLMProvider().generate_analysis(underlying, system_prompt, user_prompt)
            latency_ms = int((time.perf_counter() - start) * 1000)
            return {
                "success": True,
                "provider": "mock_ai",
                "model": "mock-deterministic-v1",
                "latency_ms": latency_ms,
                "schema_valid": True,
                "is_mock": True,
                "message": "Mock AI is deterministic and requires no external service. Prompt pipeline and schema validation passed.",
                "insight": insight.model_dump(mode="json"),
            }

        # Real providers – instantiate with supplied keys and do strict test
        underlying = symbol.upper().replace(" 50", "")
        regime = await regime_service.classify_market_regime(underlying)
        futures = await futures_service.get_futures_overview(underlying)
        try:
            chain = await options_service.get_option_chain_matrix(underlying)
            options_analytics = chain.analytics
            max_pain = chain.max_pain
        except Exception:
            options_analytics = None
            max_pain = None
        system_prompt = build_system_prompt()
        user_prompt = build_market_context_prompt(symbol=underlying, regime=regime, futures=futures, options_analytics=options_analytics, max_pain=max_pain)

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

        llm = create_provider_for_test(
            provider,
            geminiApiKey=geminiApiKey,
            geminiModel=geminiModel,
            openRouterApiKey=openRouterApiKey,
            openRouterModel=openRouterModel,
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
