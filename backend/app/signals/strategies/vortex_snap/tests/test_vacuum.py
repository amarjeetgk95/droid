"""
Unit tests for Liquidity Vacuum Detector (§10).
"""
import pytest
from app.signals.strategies.vortex_snap.features.compression import CompressionEngine
from app.signals.strategies.vortex_snap.features.vacuum import LiquidityVacuumDetector
from app.signals.strategies.vortex_snap.tests.conftest import (
    create_candle,
    generate_flat_candles,
)


class TestLiquidityVacuumDetector:
    def setup_method(self):
        self.compression_engine = CompressionEngine()
        self.vacuum_detector = LiquidityVacuumDetector()

    def test_vacuum_detection_after_compression(self):
        # 30 tight consolidation bars (range 3 pts, vol 500)
        candles = generate_flat_candles(30, base_price=24000.0, bar_range=3.0)
        comp = self.compression_engine.compute(candles)

        # Bar 31: Sudden 25-point expansion candle closing at top tick with 3x volume
        expansion_candle = create_candle(
            1758426000000 + 30 * 60000,
            24001.0,
            24027.0,
            24000.0,
            24026.5,
            volume=3500.0,
        )
        candles.append(expansion_candle)

        res = self.vacuum_detector.compute(
            candles=candles,
            compression=comp,
            prior_compression_history=[0.85] * 5,
        )

        assert 0.0 <= res.liquidity_vacuum_score <= 1.0
        assert res.range_expansion > 3.0
        assert res.volume_shock > 3.0
        assert res.close_location > 0.90  # Closed at the absolute high
        assert res.prior_compression_passed
        assert res.is_vacuum_detected
        assert res.liquidity_vacuum_score >= 0.65

    def test_no_vacuum_on_continued_compression(self):
        candles = generate_flat_candles(30, base_price=24000.0, bar_range=3.0)
        comp = self.compression_engine.compute(candles)
        res = self.vacuum_detector.compute(candles=candles, compression=comp)

        assert not res.is_vacuum_detected
        assert res.liquidity_vacuum_score < 0.40
