import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from app.models.ai import AIInsightResponse, AIHistoryItem
from app.services.regime_service import regime_service
from app.services.futures_service import futures_service
from app.services.options_service import options_service
from app.ai.prompt_builder import build_system_prompt, build_market_context_prompt
from app.ai.registry import get_llm_provider
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

        # 5. Dispatch to LLM Provider
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


ai_service = AIService()
