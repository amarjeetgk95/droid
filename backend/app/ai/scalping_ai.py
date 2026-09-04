"""
Scalping AI Module — Fast Path — §2, §3, §9

Analyzes 1M/3M opportunities with minimal context and strict latency budget.
One in-flight request per symbol; new context cancels/supersedes stale requests.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Literal
import structlog

from app.ai.schemas import (
    AISignal,
    MarketContext,
    Decision,
    SetupType,
    Regime,
    ValidationStatus,
    LatencyBreakdown,
    RejectionReason,
)
from app.ai.output_validator import ai_output_validator
from app.ai.signal_scorer import signal_scorer
from app.ai.context_builder import market_context_builder
from app.ai.provider_manager import provider_manager

logger = structlog.get_logger()

SCALPING_TIMEOUT_MS = 400
SCALPING_HARD_CEILING_MS = 500
SCALPING_MIN_TTL = 15
SCALPING_MAX_TTL = 120
SCALPING_HARD_MAX_TTL = 180

SCALPING_PROMPT = """You are DROID Scalping AI, a high-frequency momentum analysis engine.

Analyze the current market context and respond with ONLY valid JSON:
{
  "decision": "LONG|SHORT|NO_TRADE",
  "setup_type": "BREAKOUT|MOMENTUM|PULLBACK|MEAN_REVERSION|CONTINUATION|REVERSAL",
  "confidence": 0-100,
  "entry": price,
  "stop_loss": price,
  "target": price,
  "ttl_seconds": 15-120,
  "regime": "TREND|RANGE|BREAKOUT|REVERSAL|HIGH_VOLATILITY|LOW_VOLATILITY",
  "reasons": ["tag1", "tag2"],
  "invalidation": ["condition1"]
}

Rules:
- Decision must be LONG or SHORT or NO_TRADE only
- Stop loss must be on correct side of entry
- Target must be on correct side of entry
- ttl_seconds must be 15-120
- Reasons must be short tags, not prose
- If no clear setup, return NO_TRADE
- Never fabricate prices; use only provided context
"""


class InFlightRequest:
    def __init__(self, request_id: str, context_hash: str, created_at: datetime):
        self.request_id = request_id
        self.context_hash = context_hash
        self.created_at = created_at
        self.cancelled = False
        self.response_received = False


class ScalpingAI:
    """
    Fast Scalping AI module for 1M/3M opportunities.

    Per §3:
    - Minimal context (≤2KB serialized)
    - Provider timeout: 400ms hard
    - Signal TTL: 15-120s
    - One in-flight request per symbol
    - Cancellation when newer context arrives
    """

    def __init__(self):
        self._in_flight: dict[str, InFlightRequest] = {}
        self._last_context_hash: dict[str, str] = {}
        self._last_decision: dict[str, AISignal] = {}
        self._debounce_seconds = 2.0

    def _get_in_flight(self, symbol: str) -> Optional[InFlightRequest]:
        return self._in_flight.get(symbol.upper())

    def _set_in_flight(self, symbol: str, request: InFlightRequest) -> None:
        symbol = symbol.upper()
        existing = self._get_in_flight(symbol)
        if existing and not existing.cancelled:
            existing.cancelled = True
            logger.info("superseding_in_flight_request", symbol=symbol, old_request=existing.request_id)
        self._in_flight[symbol] = request

    def _clear_in_flight(self, symbol: str) -> None:
        symbol = symbol.upper()
        self._in_flight.pop(symbol, None)

    async def analyze(
        self,
        context: MarketContext,
        provider,
        symbol: str,
        timeframe: Literal["1M", "3M"] = "1M",
        override_timeout_ms: Optional[int] = None,
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

        context_hash = context.context_hash
        last_hash = self._last_context_hash.get(symbol)
        if last_hash == context_hash:
            last_signal = self._last_decision.get(symbol)
            if last_signal and not last_signal.superseded:
                last_signal.reused = True
                logger.info("reusing_cached_decision", symbol=symbol, signal_id=last_signal.signal_id)
                return last_signal

        request_id = str(uuid.uuid4())
        in_flight = InFlightRequest(request_id, context_hash, datetime.now(timezone.utc))
        self._set_in_flight(symbol, in_flight)

        try:
            serialized = context.model_dump_json()
            if len(serialized.encode()) > 2048:
                logger.warning("context_exceeds_size_cap", symbol=symbol, size=len(serialized))

            prompt = self._build_prompt(context, timeframe)

            start = time.perf_counter()
            try:
                raw_response = await asyncio.wait_for(
                    provider.generate_analysis(symbol, SCALPING_PROMPT, prompt),
                    timeout=timeout_ms / 1000.0,
                )
                provider_latency_ms = int((time.perf_counter() - start) * 1000)
            except asyncio.TimeoutError:
                provider_manager.record_failure(provider.config.provider if hasattr(provider, 'config') else 'unknown', is_timeout=True)
                logger.warning("scalping_provider_timeout", symbol=symbol, timeout_ms=timeout_ms)
                signal = self._timeout_signal(symbol, timeframe)
                return signal

            parse_start = time.perf_counter()
            signal, validation_result = ai_output_validator.validate(
                raw_response,
                path="scalping",
                expected_symbol=symbol,
                expected_timeframe=timeframe,
            )
            parse_latency_ms = int((time.perf_counter() - parse_start) * 1000)

            total_latency_ms = int((time.perf_counter() - start) * 1000)

            if in_flight.cancelled:
                signal.superseded = True
                logger.info("signal_superseded", symbol=symbol, request_id=request_id)
                return signal

            if total_latency_ms > hard_ceiling:
                logger.warning("latency_exceeded_hard_ceiling", symbol=symbol, latency_ms=total_latency_ms, ceiling=hard_ceiling)
                signal.superseded = True
                return signal

            signal.signal_id = request_id
            signal.timeframe = timeframe
            signal.latency_ms = total_latency_ms
            signal.latency_breakdown = LatencyBreakdown(
                provider_latency_ms=provider_latency_ms,
                parse_latency_ms=parse_latency_ms,
                validation_latency_ms=0,
                total_latency_ms=total_latency_ms,
            )

            if validation_result.status == ValidationStatus.PASS:
                provider_manager.record_success(provider.config.provider if hasattr(provider, 'config') else 'unknown')
                signal.validation_result = ValidationStatus.PASS
                self._last_context_hash[symbol] = context_hash
                self._last_decision[symbol] = signal
            else:
                signal.validation_result = ValidationStatus.REJECT
                signal.rejection_reason_code = validation_result.reason_code
                signal.rejection_detail = validation_result.reason_detail

            return signal

        except Exception as e:
            logger.error("scalping_analysis_error", symbol=symbol, error=str(e))
            signal = self._error_signal(symbol, timeframe, str(e))
            return signal
        finally:
            self._clear_in_flight(symbol)

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

    def _timeout_signal(self, symbol: str, timeframe: str) -> AISignal:
        now = datetime.now(timezone.utc)
        return AISignal(
            signal_id=str(uuid.uuid4()),
            symbol=symbol,
            timestamp=now,
            timeframe=timeframe,
            decision=Decision.NO_TRADE,
            validation_result=ValidationStatus.REJECT,
            rejection_reason_code=RejectionReason.PROVIDER_TIMEOUT,
            rejection_detail=f"Provider timeout after {SCALPING_TIMEOUT_MS}ms",
            ttl_seconds=SCALPING_MIN_TTL,
            expires_at=now + timedelta(seconds=SCALPING_MIN_TTL),
        )

    def _error_signal(self, symbol: str, timeframe: str, error: str) -> AISignal:
        now = datetime.now(timezone.utc)
        return AISignal(
            signal_id=str(uuid.uuid4()),
            symbol=symbol,
            timestamp=now,
            timeframe=timeframe,
            decision=Decision.NO_TRADE,
            validation_result=ValidationStatus.REJECT,
            rejection_reason_code=RejectionReason.PROVIDER_ERROR,
            rejection_detail=f"Analysis error: {error[:200]}",
            ttl_seconds=SCALPING_MIN_TTL,
            expires_at=now + timedelta(seconds=SCALPING_MIN_TTL),
        )

    def reset(self, symbol: Optional[str] = None) -> None:
        """Reset in-flight state for symbol or all."""
        if symbol:
            self._in_flight.pop(symbol.upper(), None)
            self._last_context_hash.pop(symbol.upper(), None)
            self._last_decision.pop(symbol.upper(), None)
        else:
            self._in_flight.clear()
            self._last_context_hash.clear()
            self._last_decision.clear()

    async def generate(
        self,
        symbol: str,
        regime: "Regime",
        market_context: "MarketContext",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
    ) -> "AISignal":
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
