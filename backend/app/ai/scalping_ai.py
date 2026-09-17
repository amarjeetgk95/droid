"""
Scalping AI Module — Fast Path — §2, §3, §9

Analyzes 1M/3M opportunities with minimal context and strict latency budget.
One in-flight request per symbol; new context cancels/supersedes stale requests.
"""
from __future__ import annotations

import uuid
from typing import Literal

import structlog

from app.ai.inflight import InFlightRequest, InFlightSignalMixin
from app.ai.prompt_registry import prompt_registry
from app.ai.schemas import (
    AISignal,
    Decision,
    MarketContext,
    Regime,
    SetupType,
)

logger = structlog.get_logger()

SCALPING_TIMEOUT_MS = 400
SCALPING_HARD_CEILING_MS = 500
SCALPING_MIN_TTL = 15
SCALPING_MAX_TTL = 120
SCALPING_HARD_MAX_TTL = 180

SCALPING_SYSTEM_PROMPT = prompt_registry.get("scalping").system_prompt

# InFlightRequest is re-exported here for backward compatibility (it was
# defined in this module before moving to app.ai.inflight).
__all__ = ["InFlightRequest", "InFlightSignalMixin", "ScalpingAI", "scalping_ai"]


class ScalpingAI(InFlightSignalMixin):
    """
    Fast Scalping AI module for 1M/3M opportunities.

    Per §3:
    - Minimal context (≤2KB serialized)
    - Provider timeout: 400ms hard
    - Signal TTL: 15-120s
    - One in-flight request per symbol
    - Cancellation when newer context arrives
    """

    _path = "scalping"
    _supersede_event = "superseding_in_flight_request"
    _reuse_event = "reusing_cached_decision"
    _superseded_event = "signal_superseded"
    _timeout_event = "scalping_provider_timeout"
    _hard_ceiling_event = "latency_exceeded_hard_ceiling"
    _size_event = "context_exceeds_size_cap"
    _error_event = "scalping_analysis_error"
    _timeout_detail_ms = SCALPING_TIMEOUT_MS
    _min_ttl = SCALPING_MIN_TTL

    def __init__(self):
        super().__init__(debounce_seconds=2.0)

    async def analyze(
        self,
        context: MarketContext,
        provider,
        symbol: str,
        timeframe: Literal["1M", "3M"] = "1M",
        override_timeout_ms: int | None = None,
    ) -> AISignal:
        """
        Analyze market for scalping opportunity.

        Args:
            context: Market context snapshot
            provider: AI provider instance
            symbol: Trading symbol
            timeframe: 1M or 3M
            override_timeout_ms: Override timeout (for testing)

        Returns:
            AISignal with decision and validation
        """
        symbol = symbol.upper()
        timeout_ms = override_timeout_ms or SCALPING_TIMEOUT_MS
        hard_ceiling = max(SCALPING_HARD_CEILING_MS, timeout_ms + 1000)

        return await self._run_analysis(
            context,
            provider,
            symbol,
            timeframe,
            SCALPING_SYSTEM_PROMPT,
            self._build_prompt(context, timeframe),
            timeout_ms,
            hard_ceiling,
            2048,
        )

    def _build_prompt(self, context: MarketContext, timeframe: str) -> str:
        lines = [
            f"Symbol: {context.symbol}",
            f"Timeframe: {timeframe}",
            f"Current Price: {context.current_price}",
            f"VWAP: {context.vwap}",
            f"ATR: {context.atr}",
            f"Volume: {context.volume}",
            f"Momentum: {context.momentum}",
            f"Structure 1M: {context.structure_1m}",
            f"Structure 3M: {context.structure_3m}",
            f"Regime: {context.regime.regime.value if context.regime else 'UNKNOWN'}",
            f"Market Status: {context.market_status}",
        ]
        if context.support_resistance:
            for k, v in context.support_resistance.items():
                lines.append(f"{k}: {v}")
        lines.append("\nRespond with ONLY valid JSON.")
        return "\n".join(lines)

    async def generate(
        self,
        symbol: str,
        regime: Regime,
        market_context: MarketContext,
        provider: str | None = None,
        model: str | None = None,
        openrouter_api_key: str | None = None,
        gemini_api_key: str | None = None,
    ) -> AISignal:
        """Generate a scalping signal. Returns NO_TRADE if no provider available."""
        from app.ai.provider_manager import provider_manager
        try:
            target_provider = provider or provider_manager.get_provider("scalping", ["openrouter", "gemini"])
            if not target_provider:
                return AISignal(
                    signal_id=str(uuid.uuid4()),
                    symbol=symbol.upper(),
                    decision=Decision.NO_TRADE,
                    setup_type=SetupType.SCALPING,
                    regime=regime,
                    raw_confidence=0,
                    reasons=["No AI provider configured"],
                )
            from app.ai.registry import get_llm_provider
            provider_instance = get_llm_provider(
                target_provider,
                openRouterApiKey=openrouter_api_key,
                openRouterModel=model,
                geminiApiKey=gemini_api_key,
                geminiModel=model,
                model=model,
            )
            timeout_ms = 10000 if (openrouter_api_key or gemini_api_key or model) else None
            return await self.analyze(market_context, provider_instance, symbol, timeframe="1M", override_timeout_ms=timeout_ms)
        except Exception as e:
            logger.error("scalping_generate_failed", symbol=symbol, error=str(e))
            return AISignal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol.upper(),
                decision=Decision.NO_TRADE,
                setup_type=SetupType.SCALPING,
                regime=regime,
                raw_confidence=0,
                reasons=[f"Error: {str(e)[:100]}"],
            )


scalping_ai = ScalpingAI()
