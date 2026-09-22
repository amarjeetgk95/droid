"""
Unit tests for Event Classifier (§12, §13, §14, §15).
"""
import pytest
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.signals.event_classifier import EventClassifier
from app.signals.strategies.vortex_snap.types import EventType, LevelType
from app.signals.strategies.vortex_snap.tests.conftest import create_candle, generate_flat_candles


class TestEventClassifier:
    def setup_method(self):
        self.feature_engine = VortexFeatureEngine()
        self.classifier = EventClassifier()

    def test_continuation_snap_classification(self):
        # 30 compressed bars followed by strong breakout above resistance
        candles = generate_flat_candles(30, base_price=24000.0, bar_range=4.0)
        # Bar 31: breakout candle crossing above resistance at 24020
        candles.append(create_candle(1000 + 30 * 60000, 24005.0, 24035.0, 24004.0, 24032.0, volume=4000.0))

        snapshot = self.feature_engine.compute_snapshot(
            instrument="NIFTY",
            candles_1m=candles,
            pdh=24020.0,
        )

        event = self.classifier.classify(snapshot, candles)
        assert event is not None
        assert event.event_type == EventType.CONTINUATION
        assert event.direction == 1  # LONG
        assert event.confidence >= 0.50
        assert event.interacted_level.level_type in (LevelType.PDH, LevelType.SESSION_HIGH)

    def test_vacuum_trap_failed_breakout_classification(self):
        # Scenario: Resistance is at 24100. Price pushes to 24115, but closes back at 24090.
        candles = generate_flat_candles(25, base_price=24090.0, bar_range=4.0)
        # Bar 26: Pushed through 24100 to 24115
        candles.append(create_candle(1000 + 26 * 60000, 24092.0, 24115.0, 24090.0, 24112.0, volume=2500.0))
        # Bar 27: Trap confirmation - closes back BELOW 24100 with selling pressure
        candles.append(create_candle(1000 + 27 * 60000, 24110.0, 24111.0, 24085.0, 24088.0, volume=3500.0))

        snapshot = self.feature_engine.compute_snapshot(
            instrument="NIFTY",
            candles_1m=candles,
            pdh=24100.0,
        )

        event = self.classifier.classify(snapshot, candles)
        assert event is not None
        assert event.event_type == EventType.VACUUM_TRAP
        assert event.direction == -1  # SHORT trap
        assert event.confidence >= 0.65
