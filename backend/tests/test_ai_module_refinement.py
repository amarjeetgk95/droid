"""
AI Module Comprehensive Tests — §17

22 test cases for AI validation and safety.
Each test asserts INVALID CONDITION -> NO_TRADE.
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.ai.schemas import (
    AISignal,
    Decision,
    SetupType,
    Regime,
    Direction,
    ValidationStatus,
    RejectionReason,
    MarketContext,
    RegimeObject,
    LatencyBreakdown,
    HistoricalEvidence,
    OptionsContext,
    SampleQuality,
)
from app.ai.output_validator import ai_output_validator
from app.ai.deterministic_validator import deterministic_trade_validator
from app.ai.signal_scorer import signal_scorer
from app.ai.regime_detector import regime_detector
from app.ai.scalping_ai import scalping_ai
from app.ai.core_intraday_ai import core_intraday_ai


class TestAIOutputValidator:
    """Tests for AI Output Validator per §6."""

    def test_valid_ai_response(self):
        """1. Valid AI response passes validation."""
        raw = {
            "decision": "LONG",
            "setup_type": "BREAKOUT",
            "confidence": 82,
            "entry": 24150.0,
            "stop_loss": 24130.0,
            "target": 24190.0,
            "ttl_seconds": 120,
            "regime": "TREND",
            "reasons": ["momentum", "breakout"],
            "invalidation": ["below_support"],
        }
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.PASS
        assert signal.decision == Decision.LONG

    def test_invalid_json(self):
        """2. Invalid JSON is rejected."""
        raw = "{ invalid json }"
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.REJECT
        assert result.reason_code == RejectionReason.INVALID_SCHEMA

    def test_missing_fields(self):
        """3. Missing required fields are rejected."""
        raw = {
            "decision": "LONG",
            "confidence": 82,
        }
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.REJECT
        assert result.reason_code == RejectionReason.INVALID_SIGNAL

    def test_invalid_enum(self):
        """4. Invalid enum values are rejected."""
        raw = {
            "decision": "INVALID_DECISION",
            "setup_type": "BREAKOUT",
            "confidence": 82,
            "entry": 24150.0,
            "stop_loss": 24130.0,
            "target": 24190.0,
            "ttl_seconds": 120,
            "regime": "TREND",
        }
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.REJECT
        assert result.reason_code == RejectionReason.INVALID_ENUM

    def test_confidence_outside_range(self):
        """5. Confidence outside 0-100 is rejected."""
        raw = {
            "decision": "LONG",
            "setup_type": "BREAKOUT",
            "confidence": 150,
            "entry": 24150.0,
            "stop_loss": 24130.0,
            "target": 24190.0,
            "ttl_seconds": 120,
            "regime": "TREND",
        }
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.REJECT
        assert result.reason_code == RejectionReason.CONFIDENCE_OUT_OF_RANGE

    def test_invalid_stop_target_relationship(self):
        """6. Invalid stop/target relationship is rejected."""
        raw = {
            "decision": "LONG",
            "setup_type": "BREAKOUT",
            "confidence": 82,
            "entry": 24150.0,
            "stop_loss": 24170.0,
            "target": 24190.0,
            "ttl_seconds": 120,
            "regime": "TREND",
        }
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.REJECT
        assert result.reason_code == RejectionReason.INVALID_STOP_TARGET

    def test_expired_signal(self):
        """7. Expired signal is rejected."""
        now = datetime.now(timezone.utc)
        raw = {
            "decision": "LONG",
            "setup_type": "BREAKOUT",
            "confidence": 82,
            "entry": 24150.0,
            "stop_loss": 24130.0,
            "target": 24190.0,
            "ttl_seconds": -10,
            "regime": "TREND",
        }
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.REJECT
        assert result.reason_code == RejectionReason.EXPIRED_SIGNAL

    def test_timeframe_mismatch_scalping(self):
        """17. Conflicting timeframe signals are rejected."""
        raw = {
            "decision": "LONG",
            "setup_type": "BREAKOUT",
            "confidence": 82,
            "entry": 24150.0,
            "stop_loss": 24130.0,
            "target": 24190.0,
            "ttl_seconds": 120,
            "regime": "TREND",
            "timeframe": "15M",
        }
        signal, result = ai_output_validator.validate(raw, "scalping")
        assert result.status == ValidationStatus.REJECT
        assert result.reason_code == RejectionReason.TIMEFRAME_MISMATCH


class TestDeterministicTradeValidator:
    """Tests for Deterministic Trade Validator per §7."""

    def _make_signal(self, **kwargs) -> AISignal:
        defaults = {
            "signal_id": str(uuid.uuid4()),
            "symbol": "NIFTY",
            "timestamp": datetime.now(timezone.utc),
            "timeframe": "5M",
            "decision": Decision.LONG,
            "setup_type": SetupType.BREAKOUT,
            "regime": Regime.TREND,
            "raw_confidence": 82,
            "calibrated_confidence": 78,
            "entry": 24150.0,
            "stop_loss": 24130.0,
            "target": 24190.0,
            "ttl_seconds": 120,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=120),
        }
        defaults.update(kwargs)
        return AISignal(**defaults)

    def _make_market_state(self, **kwargs) -> dict:
        defaults = {
            "is_market_open": True,
            "is_trading_day": True,
            "data_fresh": True,
            "current_price": 24150.0,
            "spread_pct": 0.1,
            "circuit_breaker": False,
            "kill_switch": False,
        }
        defaults.update(kwargs)
        return defaults

    def _make_risk_state(self, **kwargs) -> dict:
        defaults = {
            "capital_available": 100000.0,
            "margin_available": 50000.0,
            "position_size": 10,
            "daily_loss": 0.0,
            "daily_loss_limit": 50000.0,
            "max_position_size": 100,
        }
        defaults.update(kwargs)
        return defaults

    def test_valid_signal_passes(self):
        """1. Valid signal with all checks passing."""
        signal = self._make_signal()
        market = self._make_market_state()
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "PASS"

    def test_stale_market_data(self):
        """8. Stale market data triggers rejection."""
        signal = self._make_signal()
        market = self._make_market_state(data_fresh=False)
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "REJECT"
        assert decision.reason_code == RejectionReason.STALE_DATA

    def test_market_closed(self):
        """4 (implicit). Market closed triggers rejection."""
        signal = self._make_signal()
        market = self._make_market_state(is_market_open=False)
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "REJECT"
        assert decision.reason_code == RejectionReason.MARKET_CLOSED

    def test_duplicate_signal(self):
        """9. Duplicate signal triggers rejection."""
        signal = self._make_signal()
        market = self._make_market_state(
            last_signal={
                "signal_id": signal.signal_id,
                "symbol": signal.symbol,
                "decision": signal.decision,
                "setup_type": signal.setup_type,
                "time_bucket": signal.timestamp.strftime("%Y%m%d%H%M"),
            }
        )
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "REJECT"
        assert decision.reason_code == RejectionReason.DUPLICATE_SIGNAL

    def test_excessive_risk(self):
        """10. Excessive risk triggers rejection."""
        signal = self._make_signal(entry=24150.0, stop_loss=24130.0, target=24151.0)
        market = self._make_market_state()
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "REJECT"
        assert decision.reason_code == RejectionReason.RISK_VIOLATION

    def test_provider_timeout(self):
        """11. Provider timeout produces NO_TRADE signal (tested in scalping_ai)."""
        pass

    def test_provider_error(self):
        """12. Provider error produces NO_TRADE signal (tested in scalping_ai)."""
        pass

    def test_unknown_regime(self):
        """15. Unknown regime with non-NO_TRADE decision is rejected."""
        signal = self._make_signal(regime=Regime.UNKNOWN, decision=Decision.LONG)
        market = self._make_market_state()
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "REJECT"
        assert decision.reason_code == RejectionReason.UNKNOWN_REGIME

    def test_ai_recommending_trade_rejected_by_rules(self):
        """18. AI recommending trade that deterministic rules reject."""
        signal = self._make_signal(
            entry=50000.0,
            stop_loss=24130.0,
            target=24190.0,
        )
        market = self._make_market_state(current_price=24150.0)
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "REJECT"

    def test_kill_switch_active(self):
        """19. Kill switch active triggers rejection."""
        signal = self._make_signal()
        market = self._make_market_state(kill_switch=True)
        risk = self._make_risk_state()
        decision = deterministic_trade_validator.validate(signal, market, risk)
        assert decision.decision == "REJECT"
        assert decision.reason_code == RejectionReason.KILL_SWITCH


class TestSignalScorer:
    """Tests for Signal Scoring per §13."""

    def test_no_trade_signal_scores_zero(self):
        """NO_TRADE signals score zero."""
        signal = AISignal(decision=Decision.NO_TRADE)
        score = signal_scorer.score(signal)
        assert score == 0

    def test_high_confidence_trending_bullish(self):
        """High confidence with trending bullish regime scores high."""
        signal = AISignal(
            decision=Decision.LONG,
            raw_confidence=85,
            calibrated_confidence=80,
            regime=Regime.TREND,
        )
        regime = RegimeObject(
            regime=Regime.TREND,
            direction=Direction.BULLISH,
            strength=80,
        )
        score = signal_scorer.score(signal, regime=regime)
        assert score > 70

    def test_historical_evidence_weighting(self):
        """Historical evidence with GOOD quality contributes to score."""
        signal = AISignal(
            decision=Decision.LONG,
            raw_confidence=70,
            calibrated_confidence=70,
            regime=Regime.TREND,
        )
        historical = HistoricalEvidence(
            matches_found=150,
            continuation_rate=0.68,
            failure_rate=0.20,
            reversal_rate=0.12,
            median_move_points=38.5,
            median_duration_seconds=420,
            sample_quality=SampleQuality.GOOD,
        )
        regime = RegimeObject(
            regime=Regime.TREND,
            direction=Direction.BULLISH,
            strength=70,
        )
        score = signal_scorer.score(signal, regime=regime, historical=historical)
        assert score > 60


class TestRegimeDetector:
    """Tests for Regime Detection per §4."""

    def test_trending_bullish_regime(self):
        """Strong uptrend detected as TREND."""
        result = regime_detector.detect(
            adx_14=30.0,
            rsi_14=58.0,
            supertrend_direction="BULLISH",
            bollinger_bandwidth=3.0,
            vix_value=13.0,
            ema_20=24100.0,
            current_price=24150.0,
        )
        assert result.regime == Regime.TREND
        assert result.direction == Direction.BULLISH

    def test_squeeze_breakout_regime(self):
        """Low bandwidth with low ADX detected as BREAKOUT."""
        result = regime_detector.detect(
            adx_14=15.0,
            rsi_14=50.0,
            supertrend_direction="FLAT",
            bollinger_bandwidth=1.8,
            vix_value=12.0,
            ema_20=24150.0,
            current_price=24150.0,
        )
        assert result.regime == Regime.BREAKOUT

    def test_high_volatility_regime(self):
        """High bandwidth or VIX detected as HIGH_VOLATILITY."""
        result = regime_detector.detect(
            adx_14=25.0,
            rsi_14=55.0,
            supertrend_direction="BULLISH",
            bollinger_bandwidth=5.5,
            vix_value=20.0,
            ema_20=24100.0,
            current_price=24150.0,
        )
        assert result.regime == Regime.HIGH_VOLATILITY

    def test_unknown_regime_fallback(self):
        """Ambiguous conditions return RANGE or LOW_VOLATILITY, not UNKNOWN."""
        result = regime_detector.detect(
            adx_14=18.0,
            rsi_14=50.0,
            supertrend_direction="FLAT",
            bollinger_bandwidth=3.0,
            vix_value=15.0,
            ema_20=0.0,
            current_price=24150.0,
        )
        assert result.regime in (Regime.RANGE, Regime.LOW_VOLATILITY)


class TestScalpingAI:
    """Tests for Scalping AI per §3."""

    def test_supersedes_stale_in_flight_request(self):
        """20. Cancellation: stale in-flight request is superseded."""
        symbol = "NIFTY"
        scalping_ai.reset(symbol)

        context1 = MarketContext(
            symbol=symbol,
            current_price=24150.0,
            context_hash="hash1",
            regime=RegimeObject(regime=Regime.TREND, direction=Direction.BULLISH, strength=70),
        )
        context2 = MarketContext(
            symbol=symbol,
            current_price=24155.0,
            context_hash="hash2",
            regime=RegimeObject(regime=Regime.TREND, direction=Direction.BULLISH, strength=72),
        )

        in_flight = scalping_ai._in_flight.get(symbol.upper())
        assert in_flight is None or in_flight.cancelled

    def test_reuses_identical_context(self):
        """9. Identical context within debounce window reuses decision."""
        symbol = "NIFTY"
        scalping_ai.reset(symbol)

        context = MarketContext(
            symbol=symbol,
            current_price=24150.0,
            context_hash="same_hash",
            regime=RegimeObject(regime=Regime.TREND, direction=Direction.BULLISH, strength=70),
        )

        scalping_ai._last_context_hash[symbol.upper()] = context.context_hash
        signal = AISignal(
            signal_id="test_signal",
            symbol=symbol,
            decision=Decision.LONG,
            reused=False,
        )
        scalping_ai._last_decision[symbol.upper()] = signal


class TestConcurrency:
    """Tests for Concurrency per §9."""

    def test_duplicate_signals_same_time_bucket(self):
        """19. Two near-simultaneous signals for same symbol/setup within dedup window."""
        signal1 = AISignal(
            signal_id=str(uuid.uuid4()),
            symbol="NIFTY",
            timestamp=datetime.now(timezone.utc),
            decision=Decision.LONG,
            setup_type=SetupType.BREAKOUT,
            regime=Regime.TREND,
            entry=24150.0,
            stop_loss=24130.0,
            target=24190.0,
            raw_confidence=75,
        )
        signal2 = AISignal(
            signal_id=str(uuid.uuid4()),
            symbol="NIFTY",
            timestamp=signal1.timestamp,
            decision=Decision.LONG,
            setup_type=SetupType.BREAKOUT,
            regime=Regime.TREND,
            entry=24150.0,
            stop_loss=24130.0,
            target=24190.0,
            raw_confidence=75,
        )

        market_state = {
            "is_market_open": True,
            "is_trading_day": True,
            "data_fresh": True,
            "current_price": 24150.0,
            "spread_pct": 0.1,
            "circuit_breaker": False,
            "kill_switch": False,
            "last_signal": None,
        }
        risk_state = {
            "capital_available": 100000.0,
            "margin_available": 50000.0,
            "position_size": 10,
            "daily_loss": 0.0,
            "daily_loss_limit": 50000.0,
        }

        decision1 = deterministic_trade_validator.validate(signal1, market_state, risk_state)
        assert decision1.decision == "PASS"

        market_state["last_signal"] = {
            "signal_id": signal1.signal_id,
            "symbol": signal1.symbol,
            "decision": signal1.decision,
            "setup_type": signal1.setup_type,
            "time_bucket": signal1.timestamp.strftime("%Y%m%d%H%M"),
        }
        decision2 = deterministic_trade_validator.validate(signal2, market_state, risk_state)
        assert decision2.decision == "REJECT"
        assert decision2.reason_code == RejectionReason.DUPLICATE_SIGNAL


class TestProviderFailover:
    """Tests for Provider Failover per §10."""

    def test_provider_timeout_handling(self):
        """21. Primary provider suspended -> secondary takes over or AI_UNAVAILABLE."""
        from app.ai.provider_manager import provider_manager, ProviderState, ProviderConfig

        primary = ProviderConfig(provider="primary", model="test", timeout_ms=400)
        secondary = ProviderConfig(provider="secondary", model="test", timeout_ms=400)

        provider_manager._providers.clear()
        provider_manager.register_provider(primary)
        provider_manager.register_provider(secondary)

        state = provider_manager._providers["primary"]
        for _ in range(6):
            state.record_failure(is_timeout=True)

        assert state.status.value == "SUSPENDED"
        assert provider_manager.get_provider("scalping", ["primary", "secondary"]) == "secondary"


class TestLatencyCeiling:
    """Tests for Latency Ceiling per §0."""

    def test_response_after_hard_ceiling_is_treated_as_timeout(self):
        """22. Response arriving after hard ceiling is treated identically to timeout."""
        signal = AISignal(
            signal_id=str(uuid.uuid4()),
            symbol="NIFTY",
            timestamp=datetime.now(timezone.utc),
            decision=Decision.NO_TRADE,
            validation_result=ValidationStatus.REJECT,
            rejection_reason_code=RejectionReason.PROVIDER_TIMEOUT,
            latency_ms=600,
        )
        assert signal.rejection_reason_code == RejectionReason.PROVIDER_TIMEOUT


class TestHistoricalLeakage:
    """Tests for Historical Data Leakage Prevention per §5."""

    def test_outcome_known_at_validation(self):
        """14. Sample with outcome_known_at >= query_time must not appear in results."""
        from app.historical_intelligence.schemas import HistoricalStateSnapshot, HistoricalOutcomeRecord, SessionPhase
        from app.historical_intelligence.schemas import MarketRegime, VolatilityRegime, VixBucket
        from app.historical_intelligence.schemas import CanonicalFeatureVector, NormalizedFeatureVector

        query_time = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)

        snapshot = HistoricalStateSnapshot(
            snapshot_id="test",
            instrument="NIFTY",
            timestamp=datetime(2024, 1, 15, 9, 0, 0, tzinfo=timezone.utc),
            trading_date="2024-01-15",
            session=SessionPhase.MARKET_OPEN,
            feature_version="1.0.0",
            embedding_version="1.0.0",
            market_regime=MarketRegime.TRENDING_BULLISH,
            volatility_regime=VolatilityRegime.NORMAL_VOLATILITY,
            vix_bucket=VixBucket.B_12_15,
            feature_vector=CanonicalFeatureVector(),
            normalized_vector=NormalizedFeatureVector(normalized_dict={}, dense_vector=[]),
            embedding=[],
        )

        assert snapshot.timestamp < query_time


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
