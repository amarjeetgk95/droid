"""
Unit tests for Confirmation Engine (§17).
"""
import pytest
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.signals.confirmation import ConfirmationEngine
from app.signals.strategies.vortex_snap.signals.event_classifier import ClassifiedEvent
from app.signals.strategies.vortex_snap.types import EventType, LevelType, StructuralLevel
from app.signals.strategies.vortex_snap.tests.conftest import create_candle, generate_trending_candles


class TestConfirmationEngine:
    def setup_method(self):
        self.feature_engine = VortexFeatureEngine()
        self.confirmation_engine = ConfirmationEngine()

    def test_continuation_follow_through_confirmation(self):
        candles = generate_trending_candles(25)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)

        dummy_level = StructuralLevel(
            level_type=LevelType.PDH,
            price=24000.0,
            relevance_score=0.90,
            distance_points=10.0,
            distance_pct=0.0004,
            touch_count=2,
            rejection_count=0,
        )
        event = ClassifiedEvent(
            event_type=EventType.CONTINUATION,
            direction=1,
            confidence=0.80,
            interacted_level=dummy_level,
        )

        trigger_candle = create_candle(1000, 24010, 24025, 24008, 24022)
        confirm_candle = create_candle(61000, 24022, 24040, 24020, 24038)  # Closes higher

        res = self.confirmation_engine.evaluate(event, trigger_candle, confirm_candle, snapshot)
        assert res.is_confirmed
        assert res.confirmation_mechanism == "FOLLOW_THROUGH_CANDLE"
        assert res.confidence_boost > 0.0

    def test_continuation_failed_follow_through(self):
        candles = generate_trending_candles(25)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)

        dummy_level = StructuralLevel(
            level_type=LevelType.PDH,
            price=24000.0,
            relevance_score=0.90,
            distance_points=10.0,
            distance_pct=0.0004,
            touch_count=2,
            rejection_count=0,
        )
        event = ClassifiedEvent(
            event_type=EventType.CONTINUATION,
            direction=1,
            confidence=0.80,
            interacted_level=dummy_level,
        )

        trigger_candle = create_candle(1000, 24010, 24025, 24008, 24022)
        confirm_candle = create_candle(61000, 24022, 24023, 24005, 24006)  # Flushed lower

        res = self.confirmation_engine.evaluate(event, trigger_candle, confirm_candle, snapshot)
        assert not res.is_confirmed
