"""
Unit tests for Snap Energy Composite (§11).
"""
import pytest
from app.signals.strategies.vortex_snap.features.compression import CompressionEngine
from app.signals.strategies.vortex_snap.features.pressure import DirectionalPressureEngine
from app.signals.strategies.vortex_snap.features.snap_energy import SnapEnergyEngine
from app.signals.strategies.vortex_snap.types import CompressionZone
from app.signals.strategies.vortex_snap.tests.conftest import (
    create_candle,
    generate_flat_candles,
)


class TestSnapEnergyEngine:
    def setup_method(self):
        self.compression_engine = CompressionEngine()
        self.pressure_engine = DirectionalPressureEngine()
        self.energy_engine = SnapEnergyEngine()

    def test_zero_energy_on_low_duration(self):
        candles = generate_flat_candles(10)
        comp = self.compression_engine.compute(candles)
        # Force low duration (e.g. 1 bar)
        comp.duration_bars = 1
        press = self.pressure_engine.compute(candles)
        res = self.energy_engine.compute(candles, comp, press)

        assert res.snap_energy == 0.0
        assert res.energy_tier == "LOW"

    def test_high_energy_on_long_compression_with_consistent_pressure(self):
        # 25 bars of consolidation where buyers consistently absorb sellers (green bodies, high volume)
        candles: list = []
        t0 = 1000000
        for i in range(25):
            # Tightly coiled between 24000 and 24004, but closing up
            candles.append(create_candle(t0 + i * 60000, 24000.5, 24004.0, 24000.0, 24003.5, volume=2000.0))

        comp = self.compression_engine.compute(candles, prior_duration=12)
        # Ensure duration reflects 13 bars
        comp.duration_bars = 13
        press = self.pressure_engine.compute(candles)

        res = self.energy_engine.compute(candles, comp, press)

        assert 0.0 <= res.snap_energy <= 1.0
        assert res.compression_duration >= 10
        assert res.directional_consistency >= 0.80
        assert res.energy_tier in ("HIGH", "EXPLOSIVE", "MODERATE")
        assert res.snap_energy >= 0.50
