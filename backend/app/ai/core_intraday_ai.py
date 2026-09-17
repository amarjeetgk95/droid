"""
Core Intraday AI Module — §2, §3, §9

Analyzes 5M/15M opportunities with multi-timeframe context.
Shared deterministic validator as final authority.
"""
from __future__ import annotations

import uuid
from typing import Literal

import structlog

from app.ai.inflight import InFlightSignalMixin
from app.ai.prompt_registry import prompt_registry
from app.ai.schemas import (
    AISignal,
    Decision,
    HistoricalEvidence,
    MarketContext,
    OptionsContext,
    Regime,
    SetupType,
)

logger = structlog.get_logger()

CORE_TIMEOUT_MS = 2500
CORE_HARD_CEILING_MS = 3000
CORE_MIN_TTL = 120
CORE_MAX_TTL = 900
CORE_HARD_MAX_TTL = 1200

CORE_SYSTEM_PROMPT = prompt_registry.get("core_intraday").system_prompt


class CoreIntradayAI(InFlightSignalMixin):
    """
    Core Intraday AI module for 5M/15M opportunities.

    Per §3:
    - Multi-timeframe alignment
    - Regime confirmation
    - Price structure, volatility context
    - Volume confirmation
    - Options/derivatives context where available
    - Historical evidence where available
    - Provider timeout: 2500ms hard
    - Signal TTL: 120-900s
    """

    _path = "core"
    _supersede_event = "superseding_core_in_flight"
    _reuse_event = "reusing_core_cached_decision"
    _superseded_event = "core_signal_superseded"
    _timeout_event = "core_provider_timeout"
    _hard_ceiling_event = "core_latency_exceeded_hard_ceiling"
    _size_event = "core_context_exceeds_size_cap"
    _error_event = "core_analysis_error"
    _timeout_detail_ms = CORE_TIMEOUT_MS
    _min_ttl = CORE_MIN_TTL

    def __init__(self):
        super().__init__(debounce_seconds=5.0)

    async def analyze(
        self,
        context: MarketContext,
        provider,
        symbol: str,
        timeframe: Literal["5M", "15M"] = "5M",
        historical: HistoricalEvidence | None = None,
        options: OptionsContext | None = None,
        override_timeout_ms: int | None = None,
    ) -> AISignal:
        """
        Analyze market for intraday opportunity.

        Args:
            context: Market context snapshot
            provider: AI provider instance
            symbol: Trading symbol
            timeframe: 5M or 15M
            historical: Historical evidence from Historical AI
            options: Options context
            override_timeout_ms: Override timeout (for testing)

        Returns:
            AISignal with decision and validation
        """
        symbol = symbol.upper()
        timeout_ms = override_timeout_ms or CORE_TIMEOUT_MS
        hard_ceiling = max(CORE_HARD_CEILING_MS, timeout_ms + 1000)

        return await self._run_analysis(
            context,
            provider,
            symbol,
            timeframe,
            CORE_SYSTEM_PROMPT,
            self._build_prompt(context, timeframe, historical, options),
            timeout_ms,
            hard_ceiling,
            6144,
            historical=historical,
            options=options,
            score_on_pass=True,
            apply_context=True,
        )

    def _build_prompt(
        self,
        context: MarketContext,
        timeframe: str,
        historical: HistoricalEvidence | None = None,
        options: OptionsContext | None = None,
    ) -> str:
        lines = [
            f"Symbol: {context.symbol}",
            f"Timeframe: {timeframe}",
            f"Current Price: {context.current_price}",
            f"Market Status: {context.market_status}",
            "",
            "Multi-timeframe Structure:",
            f"  1M: {context.structure_1m}",
            f"  3M: {context.structure_3m}",
            f"  5M: {context.structure_5m}",
            f"  15M: {context.structure_15m}",
            "",
            "Technical Context:",
            f"  VWAP: {context.vwap}",
            f"  ATR: {context.atr}",
            f"  Volume: {context.volume}",
            f"  Momentum: {context.momentum}",
            "",
            f"Regime: {context.regime.regime.value if context.regime else 'UNKNOWN'}",
            f"Regime Direction: {context.regime.direction.value if context.regime else 'NEUTRAL'}",
            f"Regime Strength: {context.regime.strength if context.regime else 0}",
        ]

        if context.support_resistance:
            lines.append("")
            lines.append("Key Levels:")
            for k, v in context.support_resistance.items():
                lines.append(f"  {k}: {v}")

        if options:
            lines.append("")
            lines.append("Options Context:")
            lines.append(f"  PCR OI: {options.pcr_oi:.2f}")
            lines.append(f"  PCR Volume: {options.pcr_volume:.2f}")
            lines.append(f"  ATM IV: {options.atm_iv:.2f}%")
            lines.append(f"  Direction: {options.direction}")
            lines.append(f"  Breakout Confirmation: {options.breakout_confirmation}")

        if historical:
            lines.append("")
            lines.append("Historical Evidence:")
            lines.append(f"  Matches Found: {historical.matches_found}")
            lines.append(f"  Continuation Rate: {historical.continuation_rate:.2%}")
            lines.append(f"  Failure Rate: {historical.failure_rate:.2%}")
            lines.append(f"  Sample Quality: {historical.sample_quality.value}")

        lines.append("")
        lines.append("Respond with ONLY valid JSON.")

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
        """Generate a core intraday signal. Returns NO_TRADE if no provider available."""
        from app.ai.provider_manager import provider_manager
        try:
            target_provider = provider or provider_manager.get_provider("core", ["openrouter", "gemini"])
            if not target_provider:
                return AISignal(
                    signal_id=str(uuid.uuid4()),
                    symbol=symbol.upper(),
                    decision=Decision.NO_TRADE,
                    setup_type=SetupType.CONTINUATION,
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
            timeout_ms = 15000 if (openrouter_api_key or gemini_api_key or model) else None
            return await self.analyze(market_context, provider_instance, symbol, timeframe="5M", override_timeout_ms=timeout_ms)
        except Exception as e:
            logger.error("core_intraday_generate_failed", symbol=symbol, error=str(e))
            return AISignal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol.upper(),
                decision=Decision.NO_TRADE,
                setup_type=SetupType.CONTINUATION,
                regime=regime,
                raw_confidence=0,
                reasons=[f"Error: {str(e)[:100]}"],
            )


core_intraday_ai = CoreIntradayAI()
