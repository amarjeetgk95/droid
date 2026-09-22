"""
Unit tests for Absorption Detector (§9).
"""
import pytest
from app.signals.strategies.vortex_snap.features.pressure import DirectionalPressureEngine
from app.signals.strategies.vortex_snap.features.translation import TranslationRatioEngine
from app.signals.strategies.vortex_snap.features.structural_levels import StructuralLevelEngine
from app.signals.strategies.vortex_snap.features.absorption import AbsorptionDetector
from app.signals.strategies.vortex_snap.tests.conftest import create_candle


class TestAbsorptionDetector:
    def setup_method(self):
        self.pressure_engine = DirectionalPressureEngine()
        self.translation_engine = TranslationRatioEngine()
        self.structural_engine = StructuralLevelEngine()
        self.absorption_detector = AbsorptionDetector()

    def test_absorption_at_resistance(self):
        # Scenario: Price approaches resistance at 24200.
        # High volume buy pressure is met with a massive upper rejection wick and closing low.
        candles = [
            create_candle(1000 + i * 60000, 24150 + i * 4, 24150 + i * 4 + 6, 24150 + i * 4, 24150 + i * 4 + 4, volume=1000.0)
            for i in range(12)
        ]
        # Rejection candle at resistance with volume shock of 5000 and 15-point upper wick
        candles.append(create_candle(1000 + 12 * 60000, 24195, 24212, 24185, 24187, volume=5000.0))

        press = self.pressure_engine.compute(candles)
        trans = self.translation_engine.compute(candles, press)
        levels = self.structural_engine.compute(candles, pdh=24200.0)

        res = self.absorption_detector.compute(candles, press, trans, levels)

        assert 0.0 <= res.absorption_score <= 1.0
        assert res.volume_shock_ratio > 2.0
        assert res.rejection_wick_ratio > 0.40
        assert res.absorption_score > 0.45

    def test_clean_continuation_does_not_trigger_absorption(self):
        # Smooth green candles with tiny wicks and moderate volume
        candles = [
            create_candle(1000 + i * 60000, 24000 + i * 10, 24000 + i * 10 + 11, 24000 + i * 10 - 1, 24000 + i * 10 + 10, volume=1200.0)
            for i in range(15)
        ]
        press = self.pressure_engine.compute(candles)
        trans = self.translation_engine.compute(candles, press)
        levels = self.structural_engine.compute(candles, pdh=25000.0)

        res = self.absorption_detector.compute(candles, press, trans, levels)
        assert not res.is_absorption_suspected
        assert res.absorption_score < 0.40
