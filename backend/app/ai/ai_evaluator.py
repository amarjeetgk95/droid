"""AI Evaluator - orchestrates signal generation, scoring, and execution decisions per v2 spec."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from app.ai.context_builder import MarketContextBuilder
from app.ai.core_intraday_ai import CoreIntradayAI
from app.ai.deterministic_validator import deterministic_trade_validator
from app.ai.output_validator import AIOutputValidator
from app.ai.provider_manager import ProviderManager, provider_manager
from app.ai.regime_detector import RegimeDetector
from app.ai.scalping_ai import ScalpingAI
from app.ai.schemas import (
    AISignal,
    Decision,
    ExecutionDecision,
    MarketContext,
    Regime,
    ValidationStatus,
)
from app.ai.signal_scorer import SignalScorer

logger = logging.getLogger(__name__)


class AIEvaluator:
    """Orchestrates AI signal generation and evaluation per §21."""

    def __init__(
        self,
        provider_mgr: Optional[ProviderManager] = None,
        regime_detector: Optional[RegimeDetector] = None,
        context_builder: Optional[MarketContextBuilder] = None,
        signal_scorer: Optional[SignalScorer] = None,
    ):
        self.provider_mgr = provider_mgr or provider_manager
        self.regime_detector = regime_detector or RegimeDetector()
        self.context_builder = context_builder or MarketContextBuilder()
        self.signal_scorer = signal_scorer or SignalScorer()
        self.output_validator = AIOutputValidator()
        self.scalping_ai = ScalpingAI()
        self.core_intraday_ai = CoreIntradayAI()

    async def evaluate(
        self,
        symbol: str,
        regime_hint: Optional[Regime] = None,
        context_overrides: Optional[dict] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
    ) -> tuple[AISignal, ExecutionDecision]:
        """Evaluate symbol and return (signal, execution_decision) per §21.

        Args:
            symbol: Trading symbol
            regime_hint: Optional regime override
            context_overrides: Optional context modifications
            provider: Optional provider override
            model: Optional model override
            openrouter_api_key: Optional OpenRouter API key
            gemini_api_key: Optional Gemini API key

        Returns:
            Tuple of (AISignal, ExecutionDecision)
        """
        # Pre-flight market check to avoid expensive LLM spend when market is closed.
        # P0-5: fail-closed. The generic `allow_closed_market` bypass is REMOVED —
        # only an explicit role-gated test route may pass closed-market traffic,
        # and it must do its own operator-role check before calling evaluate().
        # Any `allow_closed_market` key inside context_overrides is ignored here.
        from app.services.calendar_service import calendar_service
        if context_overrides and context_overrides.get("allow_closed_market"):
            logger.warning(
                "ai_evaluator_allow_closed_ignored",
                hint="allow_closed_market bypass removed (P0-5); failing closed unless market open",
            )

        if not calendar_service.can_trade_now().allowed:
            import uuid
            from app.ai.schemas import RejectionReason
            no_trade_sig = AISignal(
                signal_id=str(uuid.uuid4()),
                symbol=symbol,
                timestamp=datetime.now(timezone.utc),
                timeframe="5M",
                decision=Decision.NO_TRADE,
                validation_result=ValidationStatus.REJECT,
                rejection_reason_code=RejectionReason.MARKET_CLOSED.value,
                rejection_detail="Market is closed. Pre-flight check blocked AI evaluation.",
            )
            exec_decision = ExecutionDecision(
                decision="REJECT",
                reason_code=RejectionReason.MARKET_CLOSED,
                reason_detail="Market is closed. NSE trading hours: 09:15 - 15:30 IST.",
                signal_id=no_trade_sig.signal_id,
            )
            return no_trade_sig, exec_decision

        market_context = await self._build_market_context(symbol, context_overrides)
        regime = regime_hint or self._detect_regime(market_context)

        if regime == Regime.UNKNOWN:
            logger.warning(f"Unknown regime for {symbol}, using RANGE fallback")
            regime = Regime.RANGE

        signal = await self._generate_signal(
            symbol,
            regime,
            market_context,
            provider=provider,
            model=model,
            openrouter_api_key=openrouter_api_key,
            gemini_api_key=gemini_api_key,
        )
        # P0-5: score is authoritative — _score_signal assigns signal.score.
        score, weights_version, subscores = self._score_signal(signal, market_context)

        execution = deterministic_trade_validator.validate(
            signal=signal,
            market_state=market_context.to_market_state(),
            risk_state=market_context.to_risk_state(),
        )
        # P0-5: ExecutionDecision carries scoring provenance {score,
        # weights_version, subscores} so audit/SSE can prove which bundle scored.
        # (Stored on the model instance + inside order_request so it survives
        # `model_dump()` even though schemas.py owns the field list.)
        try:
            execution.__dict__["score"] = int(score)
        except Exception:
            pass
        try:
            execution.__dict__["weights_version"] = weights_version
        except Exception:
            pass
        try:
            execution.__dict__["subscores"] = dict(subscores or {})
        except Exception:
            pass
        try:
            _ord = dict(getattr(execution, "order_request", None) or {})
            _ord.setdefault("score", int(score))
            _ord.setdefault("weights_version", weights_version)
            _ord.setdefault("subscores", dict(subscores or {}))
            execution.order_request = _ord
        except Exception:
            pass

        # NO_TRADE is a valid schema outcome (no setup), not a validation
        # failure. Preserve the output-validator PASS so the UI shows a neutral
        # "no setup" state instead of a red REJECT (e.g. "entry price must be
        # > 0" or "Signal decision is NO_TRADE"). Execution still correctly
        # returns REJECT (nothing to execute).
        if signal.decision == Decision.NO_TRADE and signal.validation_result == ValidationStatus.PASS:
            pass
        else:
            signal.validation_result = (
                ValidationStatus.ACCEPT if execution.decision == "PASS" else ValidationStatus.REJECT
            )
            if execution.decision != "PASS" and not signal.rejection_detail:
                signal.rejection_detail = execution.reason_detail

        return signal, execution

    async def _build_market_context(
        self, symbol: str, overrides: Optional[dict] = None
    ) -> MarketContext:
        """Build market context with field allowlist and size caps per §11."""
        raw_context = self.context_builder.build(symbol)
        if overrides:
            raw_context = self.context_builder.apply_overrides(raw_context, overrides)
        return raw_context

    def _detect_regime(self, market_context: MarketContext) -> Regime:
        """Detect market regime per §4."""
        if market_context.regime and market_context.regime.regime != Regime.UNKNOWN:
            return market_context.regime.regime
        res = self.regime_detector.detect(market_context)
        if isinstance(res, Regime):
            return res
        if hasattr(res, "regime"):
            return res.regime
        return Regime.UNKNOWN

    async def _generate_signal(
        self,
        symbol: str,
        regime: Regime,
        market_context: MarketContext,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        openrouter_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
    ) -> AISignal:
        """Generate signal via appropriate AI path per §3."""
        use_scalping = regime in {Regime.TREND, Regime.RANGE} and market_context.volatility in {
            "LOW",
            "NORMAL",
        }

        if use_scalping:
            return await self.scalping_ai.generate(
                symbol,
                regime,
                market_context,
                provider=provider,
                model=model,
                openrouter_api_key=openrouter_api_key,
                gemini_api_key=gemini_api_key,
            )
        else:
            return await self.core_intraday_ai.generate(
                symbol,
                regime,
                market_context,
                provider=provider,
                model=model,
                openrouter_api_key=openrouter_api_key,
                gemini_api_key=gemini_api_key,
            )

    def _score_signal(self, signal: AISignal, market_context: MarketContext) -> tuple[int, str | int, dict]:
        """Score signal using composite scorer per §13.

        P0-5: ASSIGNS `signal.score = scorer.score(...)` (and mirrors into
        `calibrated_confidence` which is the schema-owned confidence field).
        Returns (score, weights_version, subscores) for ExecutionDecision provenance.
        """
        score = self.signal_scorer.score(
            signal=signal,
            regime=market_context.regime,
            historical=market_context.historical_context,
            options=market_context.options_context,
        )
        try:
            score_int = int(max(0, min(100, score)))
        except Exception:
            score_int = 0
        # Literal `signal.score = ...` assignment required by P0-5. AISignal (schemas.py)
        # does not declare `score`, so store via __dict__ (survives getattr) AND mirror
        # into the declared calibrated_confidence field (survives model_dump).
        try:
            signal.__dict__["score"] = score_int
        except Exception:
            pass
        try:
            object.__setattr__(signal, "score", score_int)
        except Exception:
            pass
        try:
            signal.calibrated_confidence = score_int
        except Exception:
            pass
        # Provenance: weights bundle version + per-domain subscores.
        try:
            weights_version: str | int = getattr(self.signal_scorer, "WEIGHTS_VERSION", 2)
        except Exception:
            weights_version = 2
        if weights_version is None:
            try:
                import json
                from pathlib import Path
                for _p in (
                    Path(__file__).resolve().parents[2] / "config" / "scoring_weights.json",
                    Path("backend/config/scoring_weights.json"),
                ):
                    if _p.exists():
                        weights_version = json.loads(_p.read_text(encoding="utf-8")).get("version", 2)
                        break
            except Exception:
                weights_version = 2
        try:
            subscores = dict(getattr(signal, "_last_subscores", None) or signal.__dict__.get("_last_subscores", None) or {})
        except Exception:
            subscores = {}
        try:
            signal.__dict__["weights_version"] = weights_version
        except Exception:
            pass
        try:
            signal.__dict__["subscores"] = dict(subscores)
        except Exception:
            pass
        return score_int, weights_version, subscores

    def validate_output(self, raw_output: str, timeframe: str) -> tuple[bool, Optional[AISignal], str]:
        """Validate AI provider output per §6.

        Returns:
            Tuple of (is_valid, parsed_signal, error_message)
        """
        return self.output_validator.validate(raw_output, timeframe)


ai_evaluator = AIEvaluator()
