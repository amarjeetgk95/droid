"""
Signal Scoring — §2, §13, §21

Combines evidence from AI analysis + regime + historical + options to produce score 0-100.
Pure function, no I/O.
"""
from __future__ import annotations

from typing import Optional
import structlog

from app.ai.schemas import (
    AISignal,
    RegimeObject,
    HistoricalEvidence,
    OptionsContext,
    SampleQuality,
    Regime,
    Direction,
    Decision,
)

logger = structlog.get_logger()

DEFAULT_EXECUTION_THRESHOLD = 70
MIN_HISTORICAL_QUALITY_FOR_WEIGHT = SampleQuality.GOOD


class SignalScorer:
    """
    Combines evidence from AI analysis, regime, historical, and options to score signal.

    Per §2: Pure function, no I/O.
    Per §13: Signal Scoring must not treat continuation_rate as win-probability substitute.
    """

    REGIME_ALIGNMENT_WEIGHT = 0.20
    HISTORICAL_WEIGHT = 0.15
    OPTIONS_WEIGHT = 0.10
    CONFIDENCE_WEIGHT = 0.25
    STRUCTURE_WEIGHT = 0.15
    DIRECTION_ALIGNMENT_WEIGHT = 0.15

    def score(
        self,
        signal: AISignal,
        regime: Optional[RegimeObject] = None,
        historical: Optional[HistoricalEvidence] = None,
        options: Optional[OptionsContext] = None,
    ) -> int:
        """
        Compute composite score 0-100.

        Args:
            signal: Validated AI signal
            regime: Market regime object
            historical: Historical evidence from Historical AI
            options: Options context

        Returns:
            Composite score 0-100
        """
        if signal.decision == Decision.NO_TRADE:
            return 0

        confidence_score = self._score_confidence(signal)
        regime_score = self._score_regime_alignment(signal, regime)
        structure_score = self._score_structure_alignment(signal, regime)
        direction_score = self._score_direction_alignment(signal, regime)
        historical_score = self._score_historical(historical)
        options_score = self._score_options(options, signal)

        raw_score = (
            confidence_score * self.CONFIDENCE_WEIGHT
            + regime_score * self.REGIME_ALIGNMENT_WEIGHT
            + structure_score * self.STRUCTURE_WEIGHT
            + direction_score * self.DIRECTION_ALIGNMENT_WEIGHT
            + historical_score * self.HISTORICAL_WEIGHT
            + options_score * self.OPTIONS_WEIGHT
        )

        return min(100, max(0, int(raw_score)))

    def _score_confidence(self, signal: AISignal) -> float:
        calibrated = signal.calibrated_confidence or signal.raw_confidence
        return float(calibrated)

    def _score_regime_alignment(self, signal: AISignal, regime: Optional[RegimeObject]) -> float:
        if regime is None:
            return 50.0

        if signal.regime == Regime.UNKNOWN:
            return 0.0

        if regime.regime == signal.regime:
            regime_match = 100.0
        elif regime.regime == Regime.TREND and signal.regime in (Regime.BREAKOUT, Regime.CONTINUATION):
            regime_match = 80.0
        elif regime.regime == Regime.RANGE and signal.regime in (Regime.LOW_VOLATILITY, Regime.HIGH_VOLATILITY):
            regime_match = 60.0
        else:
            regime_match = 30.0

        strength_factor = regime.strength / 100.0
        return regime_match * (0.5 + 0.5 * strength_factor)

    def _score_structure_alignment(self, signal: AISignal, regime: Optional[RegimeObject]) -> float:
        if regime is None:
            return 50.0

        base_score = 50.0

        if signal.setup_type.value in ("BREAKOUT", "MOMENTUM"):
            if regime.regime in (Regime.BREAKOUT, Regime.HIGH_VOLATILITY, Regime.TREND):
                base_score = 85.0
            elif regime.regime == Regime.RANGE:
                base_score = 60.0
        elif signal.setup_type.value in ("MEAN_REVERSION", "PULLBACK"):
            if regime.regime in (Regime.RANGE, Regime.LOW_VOLATILITY):
                base_score = 80.0
            elif regime.regime == Regime.TREND:
                base_score = 50.0
        elif signal.setup_type.value in ("CONTINUATION",):
            if regime.regime == Regime.TREND:
                base_score = 85.0
            else:
                base_score = 50.0
        elif signal.setup_type.value in ("REVERSAL",):
            if regime.regime == Regime.REVERSAL:
                base_score = 80.0
            else:
                base_score = 40.0

        return base_score

    def _score_direction_alignment(self, signal: AISignal, regime: Optional[RegimeObject]) -> float:
        if regime is None:
            return 50.0

        if regime.direction == Direction.NEUTRAL:
            return 50.0

        if signal.decision == Decision.LONG and regime.direction == Direction.BULLISH:
            return 100.0
        elif signal.decision == Decision.SHORT and regime.direction == Direction.BEARISH:
            return 100.0
        elif signal.decision == Decision.LONG and regime.direction == Direction.BEARISH:
            return 0.0
        elif signal.decision == Decision.SHORT and regime.direction == Direction.BULLISH:
            return 0.0
        else:
            return 50.0

    def _score_historical(self, historical: Optional[HistoricalEvidence]) -> float:
        if historical is None:
            return 50.0

        if historical.sample_quality == SampleQuality.POOR:
            return 30.0
        elif historical.sample_quality == SampleQuality.FAIR:
            return 50.0
        elif historical.sample_quality == SampleQuality.GOOD:
            continuation = historical.continuation_rate
            if continuation >= 0.65:
                return 80.0
            elif continuation >= 0.55:
                return 70.0
            elif continuation >= 0.45:
                return 55.0
            else:
                return 40.0
        return 50.0

    def _score_options(self, options: Optional[OptionsContext], signal: AISignal) -> float:
        if options is None:
            return 50.0

        base_score = 50.0

        direction_aligned = False
        if signal.decision == Decision.LONG and options.direction == "BULLISH":
            direction_aligned = True
        elif signal.decision == Decision.SHORT and options.direction == "BEARISH":
            direction_aligned = True

        if direction_aligned:
            if options.breakout_confirmation in ("BULLISH_CONFIRMED", "BEARISH_CONFIRMED"):
                base_score = 85.0
            else:
                base_score = 70.0
        else:
            base_score = 40.0

        pcr_pressure = abs(options.call_pressure - options.put_pressure)
        if pcr_pressure > 20:
            base_score = min(100, base_score + 10)

        return base_score


signal_scorer = SignalScorer()
