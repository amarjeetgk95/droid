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
        self._score_signal(signal, market_context)

        execution = deterministic_trade_validator.validate(
            signal=signal,
            market_state=market_context.to_market_state(),
            risk_state=market_context.to_risk_state(),
        )

        signal.validation_result = (
            ValidationStatus.ACCEPT if execution.decision == "PASS" else ValidationStatus.REJECT
        )

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

    def _score_signal(self, signal: AISignal, market_context: MarketContext) -> None:
        """Score signal using composite scorer per §13."""
        self.signal_scorer.score(
            signal=signal,
            regime=market_context.regime,
            historical=market_context.historical_context,
            options=market_context.options_context,
        )

    def validate_output(self, raw_output: str, timeframe: str) -> tuple[bool, Optional[AISignal], str]:
        """Validate AI provider output per §6.

        Returns:
            Tuple of (is_valid, parsed_signal, error_message)
        """
        return self.output_validator.validate(raw_output, timeframe)


ai_evaluator = AIEvaluator()
