"""
Unit tests for Directional Pressure Engine (§7).
"""
import pytest
from app.signals.strategies.vortex_snap.features.pressure import DirectionalPressureEngine
from app.signals.strategies.vortex_snap.tests.conftest import create_candle


class TestDirectionalPressureEngine:
    def setup_method(self):
        self.engine = DirectionalPressureEngine()

    def test_bullish_pressure_generation(self):
        # 15 strong green candles with large body and heavy volume
        candles = [
            create_candle(1000 + i * 60000, 24000 + i * 10, 24000 + i * 10 + 12, 24000 + i * 10, 24000 + i * 10 + 10, volume=3000.0)
            for i in range(15)
        ]
        res = self.engine.compute(candles)

        assert res.net_pressure > 0
        assert res.pressure_score > 0.30
        assert res.pressure_direction == 1
        assert res.positive_pressure > res.negative_pressure

    def test_bearish_pressure_generation(self):
        # 15 strong red candles with heavy volume
        candles = [
            create_candle(1000 + i * 60000, 24200 - i * 10, 24200 - i * 10 + 1, 24200 - i * 10 - 11, 24200 - i * 10 - 10, volume=3000.0)
            for i in range(15)
        ]
        res = self.engine.compute(candles)

        assert res.net_pressure < 0
        assert res.pressure_score < -0.30
        assert res.pressure_direction == -1
        assert res.negative_pressure > res.positive_pressure

    def test_persistence_accumulation(self):
        # Bullish candles with prior persistence of 3
        candles = [
            create_candle(1000 + i * 60000, 24000 + i * 10, 24000 + i * 10 + 12, 24000 + i * 10, 24000 + i * 10 + 10, volume=2000.0)
            for i in range(10)
        ]
        res = self.engine.compute(candles, prior_persistence=3)
        assert res.pressure_persistence == 4

    def test_flat_doji_candles_neutral_pressure(self):
        # Candles where open == close (doji)
        candles = [
            create_candle(1000 + i * 60000, 24000, 24005, 23995, 24000, volume=1000.0)
            for i in range(10)
        ]
        res = self.engine.compute(candles)
        assert res.net_pressure == 0.0
        assert res.pressure_score == 0.0
        assert res.pressure_direction == 0
