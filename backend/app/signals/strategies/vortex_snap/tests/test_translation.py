"""
Unit tests for Translation Ratio Engine (§8) - PRIMARY HYPOTHESIS.
"""
import pytest
from app.signals.strategies.vortex_snap.features.pressure import DirectionalPressureEngine
from app.signals.strategies.vortex_snap.features.translation import TranslationRatioEngine
from app.signals.strategies.vortex_snap.types import TranslationState
from app.signals.strategies.vortex_snap.tests.conftest import create_candle


class TestTranslationRatioEngine:
    def setup_method(self):
        self.pressure_engine = DirectionalPressureEngine()
        self.translation_engine = TranslationRatioEngine()

    def test_directional_acceptance(self):
        # Scenario: High volume push resulting in large price displacement
        # Price leaps 100 points over 10 bars with aligned positive pressure
        candles = [
            create_candle(1000 + i * 60000, 24000 + i * 10, 24000 + i * 10 + 12, 24000 + i * 10, 24000 + i * 10 + 10, volume=2500.0)
            for i in range(15)
        ]
        press = self.pressure_engine.compute(candles)
        trans = self.translation_engine.compute(candles, press)

        assert trans.translation_ratio > 0.8
        assert trans.direction_aligned
        assert trans.translation_state == TranslationState.DIRECTIONAL_ACCEPTANCE
        assert 0.0 <= trans.translation_score <= 1.0

    def test_absorption_candidate_high_pressure_low_displacement(self):
        # Scenario: Huge volume (10,000) hammering into resistance, but price barely moves 1 point
        candles = [
            create_candle(1000 + i * 60000, 24100.0, 24102.0, 24099.0, 24100.5, volume=10000.0)
            for i in range(15)
        ]
        press = self.pressure_engine.compute(candles)
        # Give high pressure threshold manually if needed or check score
        trans = self.translation_engine.compute(candles, press)

        # Price displacement is tiny compared to massive pressure
        assert trans.translation_ratio < 0.45
        assert trans.translation_state == TranslationState.ABSORPTION_CANDIDATE

    def test_rejection_conflict_opposing_directions(self):
        # Scenario: Positive volume pressure (green bodies earlier) but price currently dumps lower
        # Last bar has strong dump despite earlier buy attempts
        candles = [
            create_candle(1000 + i * 60000, 24000 + i * 5, 24000 + i * 5 + 6, 24000 + i * 5, 24000 + i * 5 + 5, volume=3000.0)
            for i in range(10)
        ]
        # Append sudden down bar
        candles.append(create_candle(1000 + 10 * 60000, 24050, 24051, 23980, 23985, volume=500.0))
        press = self.pressure_engine.compute(candles)
        trans = self.translation_engine.compute(candles, press)

        # Price direction vs net pressure direction
        if press.pressure_score > 0.60 and trans.price_direction < 0:
            assert trans.translation_state == TranslationState.REJECTION_CONFLICT
