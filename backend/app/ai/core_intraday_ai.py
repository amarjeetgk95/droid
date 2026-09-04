"""
Core Intraday AI Module — §2, §3, §9

Analyzes 5M/15M opportunities with multi-timeframe context.
Shared deterministic validator as final authority.
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
    HistoricalEvidence,
    OptionsContext,
)
from app.ai.output_validator import ai_output_validator
from app.ai.signal_scorer import signal_scorer
from app.ai.context_builder import market_context_builder
from app.ai.provider_manager import provider_manager

logger = structlog.get_logger()

CORE_TIMEOUT_MS = 2500
CORE_HARD_CEILING_MS = 3000
CORE_MIN_TTL = 120
CORE_MAX_TTL = 900
CORE_HARD_MAX_TTL = 1200

CORE_PROMPT = """You are DROID Core Intraday AI, a multi-timeframe institutional analysis engine.

Analyze the current market context and respond with ONLY valid JSON:
{
  "decision": "LONG|SHORT|NO_TRADE",
  "setup_type": "BREAKOUT|PULLBACK|MOMENTUM|MEAN_REVERSION|CONTINUATION|REVERSAL|GAP_FILL|VOLATILITY_CONTRACTION",
  "confidence": 0-100,
  "entry": price,
  "stop_loss": price,
  "target": price,
  "ttl_seconds": 120-900,
  "regime": "TREND|RANGE|BREAKOUT|REVERSAL|HIGH_VOLATILITY|LOW_VOLATILITY",
  "reasons": ["tag1", "tag2"],
  "invalidation": ["condition1"]
}

Multi-timeframe requirements:
- Align 5M/15M structure confirmation
- Consider regime consistency across timeframes
- Include volume confirmation
- Reference key support/resistance levels
- Consider options context if available
- Reference historical evidence if available

Rules:
- Decision must be LONG or SHORT or NO_TRADE only
- Stop loss must be on correct side of entry
- Target must be on correct side of entry
- ttl_seconds must be 120-900
- Reasons must be short tags, not prose
- If no clear setup, return NO_TRADE
"""


class CoreIntradayAI:
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

    def __init__(self):
        self._in_flight: dict[str, dict] = {}
        self._last_context_hash: dict[str, str] = {}
        self._last_decision: dict[str, AISignal] = {}
        self._debounce_seconds = 5.0

    def _get_in_flight(self, symbol: str) -> Optional[dict]:
        return self._in_flight.get(symbol.upper())

    def _set_in_flight(self, symbol: str, request: dict) -> None:
        symbol = symbol.upper()
        existing = self._get_in_flight(symbol)
        if existing:
            existing["cancelled"] = True
            logger.info("superseding_core_in_flight", symbol=symbol)
        self._in_flight[symbol] = request

    def _clear_in_flight(self, symbol: str) -> None:
        self._in_flight.pop(symbol.upper(), None)

    async def analyze(
        self,
        context: MarketContext,
        provider,
        symbol: str,
        timeframe: Literal["5M", "15M"] = "5M",
        historical: Optional[HistoricalEvidence] = None,
        options: Optional[OptionsContext] = None,
        override_timeout_ms: Optional[int] = None,
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
        hard_ceiling = CORE_HARD_CEILING_MS

        context_hash = context.context_hash
        last_hash = self._last_context_hash.get(symbol)
        if last_hash == context_hash:
            last_signal = self._last_decision.get(symbol)
            if last_signal and not last_signal.superseded:
                last_signal.reused = True
                logger.info("reusing_core_cached_decision", symbol=symbol, signal_id=last_signal.signal_id)
                return last_signal

        request_id = str(uuid.uuid4())
        in_flight = {
            "request_id": request_id,
            "context_hash": context_hash,
            "created_at": datetime.now(timezone.utc),
            "cancelled": False,
        }
        self._set_in_flight(symbol, in_flight)

        try:
            serialized = context.model_dump_json()
            if len(serialized.encode()) > 6144:
                logger.warning("core_context_exceeds_size_cap", symbol=symbol, size=len(serialized))

            prompt = self._build_prompt(context, timeframe, historical, options)

            start = time.perf_counter()
            try:
                raw_response = await asyncio.wait_for(
                    provider.generate_analysis(symbol, CORE_PROMPT, prompt),
                    timeout=timeout_ms / 1000.0,
                )
                provider_latency_ms = int((time.perf_counter() - start) * 1000)
            except asyncio.TimeoutError:
                provider_manager.record_failure(provider.config.provider if hasattr(provider, 'config') else 'unknown', is_timeout=True)
                logger.warning("core_provider_timeout", symbol=symbol, timeout_ms=timeout_ms)
                signal = self._timeout_signal(symbol, timeframe)
                return signal

            parse_start = time.perf_counter()
            signal, validation_result = ai_output_validator.validate(
                raw_response,
                path="core",
                expected_symbol=symbol,
                expected_timeframe=timeframe,
            )
            parse_latency_ms = int((time.perf_counter() - parse_start) * 1000)

            total_latency_ms = int((time.perf_counter() - start) * 1000)

            if in_flight["cancelled"]:
                signal.superseded = True
                logger.info("core_signal_superseded", symbol=symbol, request_id=request_id)
                return signal

            if total_latency_ms > hard_ceiling:
                logger.warning("core_latency_exceeded_hard_ceiling", symbol=symbol, latency_ms=total_latency_ms, ceiling=hard_ceiling)
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

            signal.historical_context = historical
            signal.options_context = options

            if validation_result.status == ValidationStatus.PASS:
                provider_manager.record_success(provider.config.provider if hasattr(provider, 'config') else 'unknown')
                signal.validation_result = ValidationStatus.PASS

                score = signal_scorer.score(signal, context.regime, historical, options)
                signal.calibrated_confidence = score

                self._last_context_hash[symbol] = context_hash
                self._last_decision[symbol] = signal
            else:
                signal.validation_result = ValidationStatus.REJECT
                signal.rejection_reason_code = validation_result.reason_code
                signal.rejection_detail = validation_result.reason_detail

            return signal

        except Exception as e:
            logger.error("core_analysis_error", symbol=symbol, error=str(e))
            signal = self._error_signal(symbol, timeframe, str(e))
            return signal
        finally:
            self._clear_in_flight(symbol)

    def _build_prompt(
        self,
        context: MarketContext,
        timeframe: str,
        historical: Optional[HistoricalEvidence] = None,
        options: Optional[OptionsContext] = None,
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
            rejection_detail=f"Provider timeout after {CORE_TIMEOUT_MS}ms",
            ttl_seconds=CORE_MIN_TTL,
            expires_at=now + timedelta(seconds=CORE_MIN_TTL),
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
            ttl_seconds=CORE_MIN_TTL,
            expires_at=now + timedelta(seconds=CORE_MIN_TTL),
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
    ) -> "AISignal":
        """Generate a core intraday signal. Uses analyze internally."""
        from app.ai.provider_manager import provider_manager
        provider = provider_manager.get_primary_provider()
        if not provider:
            return AISignal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol.upper(),
                decision=Decision.NO_TRADE,
                setup_type=SetupType.CONTINUATION,
                regime=regime,
                raw_confidence=0,
                reasons=["No AI provider available"],
            )
        return await self.analyze(market_context, provider, symbol, timeframe="5M")


core_intraday_ai = CoreIntradayAI()
