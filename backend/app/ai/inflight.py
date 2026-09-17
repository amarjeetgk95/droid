"""
Shared in-flight/cancellation/debounce machinery for the specialized desk AIs.

CoreIntradayAI and ScalpingAI each enforce "one in-flight request per symbol";
a newer context supersedes and cancels stale requests, and identical contexts
reuse the last accepted decision. This module owns that state machine plus the
shared validate/score/persist orchestration so both desks cannot drift.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog

from app.ai.output_validator import ai_output_validator
from app.ai.provider_manager import provider_manager
from app.ai.schemas import (
    AISignal,
    Decision,
    LatencyBreakdown,
    RejectionReason,
    ValidationStatus,
)
from app.ai.signal_scorer import signal_scorer

logger = structlog.get_logger()


class InFlightRequest:
    def __init__(self, request_id: str, context_hash: str, created_at: datetime):
        self.request_id = request_id
        self.context_hash = context_hash
        self.created_at = created_at
        self.cancelled = False
        self.response_received = False


class InFlightSignalMixin:
    """One in-flight request per symbol; a newer request cancels the stale one."""

    # Per-desk event names (overridden by subclasses so logs stay greppable).
    _path = "core"
    _supersede_event = "superseding_in_flight_request"
    _reuse_event = "reusing_cached_decision"
    _superseded_event = "signal_superseded"
    _timeout_event = "provider_timeout"
    _hard_ceiling_event = "latency_exceeded_hard_ceiling"
    _size_event = "context_exceeds_size_cap"
    _error_event = "analysis_error"
    _timeout_detail_ms = 400
    _min_ttl = 15

    def __init__(self, debounce_seconds: float = 0.0):
        self._in_flight: dict[str, InFlightRequest] = {}
        self._last_context_hash: dict[str, str] = {}
        self._last_decision: dict[str, AISignal] = {}
        self._debounce_seconds = debounce_seconds

    def _get_in_flight(self, symbol: str) -> InFlightRequest | None:
        return self._in_flight.get(symbol.upper())

    def _set_in_flight(self, symbol: str, request: InFlightRequest) -> None:
        symbol = symbol.upper()
        existing = self._get_in_flight(symbol)
        if existing and not existing.cancelled:
            existing.cancelled = True
            logger.info(self._supersede_event, symbol=symbol, old_request=existing.request_id)
        self._in_flight[symbol] = request

    def _clear_in_flight(self, symbol: str) -> None:
        self._in_flight.pop(symbol.upper(), None)

    def _check_cached_decision(self, symbol: str, context_hash: str) -> AISignal | None:
        if self._last_context_hash.get(symbol) == context_hash:
            last_signal = self._last_decision.get(symbol)
            if last_signal and not last_signal.superseded:
                last_signal.reused = True
                logger.info(self._reuse_event, symbol=symbol, signal_id=last_signal.signal_id)
                return last_signal
        return None

    def _remember_decision(self, symbol: str, context_hash: str, signal: AISignal) -> None:
        self._last_context_hash[symbol] = context_hash
        self._last_decision[symbol] = signal

    async def _run_analysis(
        self,
        context,
        provider,
        symbol: str,
        timeframe: str,
        system_prompt: str,
        prompt: str,
        timeout_ms: int,
        hard_ceiling_ms: int,
        size_cap: int,
        historical: Any | None = None,
        options: Any | None = None,
        score_on_pass: bool = False,
        apply_context: bool = False,
    ) -> AISignal:
        """Shared provider-call/validate/score/persist pipeline for desk signals."""
        symbol = symbol.upper()
        context_hash = context.context_hash

        cached = self._check_cached_decision(symbol, context_hash)
        if cached is not None:
            return cached

        request_id = str(uuid.uuid4())
        in_flight = InFlightRequest(request_id, context_hash, datetime.now(timezone.utc))
        self._set_in_flight(symbol, in_flight)

        try:
            serialized = context.model_dump_json()
            if len(serialized.encode()) > size_cap:
                logger.warning(self._size_event, symbol=symbol, size=len(serialized))

            start = time.perf_counter()
            try:
                raw_response = await asyncio.wait_for(
                    provider.generate_analysis(symbol, system_prompt, prompt),
                    timeout=timeout_ms / 1000.0,
                )
                provider_latency_ms = int((time.perf_counter() - start) * 1000)
            except asyncio.TimeoutError:
                provider_manager.record_failure(
                    provider.config.provider if hasattr(provider, "config") else "unknown",
                    is_timeout=True,
                )
                logger.warning(self._timeout_event, symbol=symbol, timeout_ms=timeout_ms)
                return self._timeout_signal(symbol, timeframe)

            parse_start = time.perf_counter()
            signal, validation_result = ai_output_validator.validate(
                raw_response,
                path=self._path,
                expected_symbol=symbol,
                expected_timeframe=timeframe,
            )
            parse_latency_ms = int((time.perf_counter() - parse_start) * 1000)
            total_latency_ms = int((time.perf_counter() - start) * 1000)

            if in_flight.cancelled:
                signal.superseded = True
                logger.info(self._superseded_event, symbol=symbol, request_id=request_id)
                return signal

            if total_latency_ms > hard_ceiling_ms:
                logger.warning(
                    self._hard_ceiling_event,
                    symbol=symbol,
                    latency_ms=total_latency_ms,
                    ceiling=hard_ceiling_ms,
                )
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

            if apply_context:
                signal.historical_context = historical
                signal.options_context = options

            if validation_result.status == ValidationStatus.PASS:
                provider_manager.record_success(
                    provider.config.provider if hasattr(provider, "config") else "unknown"
                )
                signal.validation_result = ValidationStatus.PASS
                if score_on_pass:
                    signal.calibrated_confidence = signal_scorer.score(signal, context.regime, historical, options)
                self._remember_decision(symbol, context_hash, signal)
            else:
                signal.validation_result = ValidationStatus.REJECT
                signal.rejection_reason_code = validation_result.reason_code
                signal.rejection_detail = validation_result.reason_detail

            return signal

        except Exception as e:
            logger.error(self._error_event, symbol=symbol, error=str(e))
            return self._error_signal(symbol, timeframe, str(e))
        finally:
            self._clear_in_flight(symbol)

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
            rejection_detail=f"Provider timeout after {self._timeout_detail_ms}ms",
            ttl_seconds=self._min_ttl,
            expires_at=now + timedelta(seconds=self._min_ttl),
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
            ttl_seconds=self._min_ttl,
            expires_at=now + timedelta(seconds=self._min_ttl),
        )

    def reset(self, symbol: str | None = None) -> None:
        """Reset in-flight state for symbol or all."""
        if symbol:
            self._in_flight.pop(symbol.upper(), None)
            self._last_context_hash.pop(symbol.upper(), None)
            self._last_decision.pop(symbol.upper(), None)
        else:
            self._in_flight.clear()
            self._last_context_hash.clear()
            self._last_decision.clear()
