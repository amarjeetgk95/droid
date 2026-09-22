"""
Unit tests for Compression Engine (§6).
"""
import pytest
from app.signals.strategies.vortex_snap.features.compression import CompressionEngine
from app.signals.strategies.vortex_snap.types import CompressionZone
from app.signals.strategies.vortex_snap.tests.conftest import (
    create_candle,
    generate_flat_candles,
    generate_trending_candles,
)


class TestCompressionEngine:
    def setup_method(self):
        self.engine = CompressionEngine()

    def test_compression_score_on_tight_consolidation(self):
        # 40 bars of tight 3-point range consolidation
        candles = generate_flat_candles(40, base_price=24000.0, bar_range=3.0)
        res = self.engine.compute(candles)

        assert 0.0 <= res.compression_score <= 1.0
        # Should be in WATCH zone (>= 0.55)
        assert res.compression_score >= 0.55
        assert res.zone in (CompressionZone.WATCH, CompressionZone.ARMED, CompressionZone.EXTREME)
        assert res.candle_overlap > 0.40

    def test_severe_compression_after_high_volatility(self):
        # 20 bars of wide 25-point ranges followed by 20 bars of tight 3-point range
        wide_candles = [
            create_candle(1000 + i * 60000, 24000 + (i % 2) * 20, 24000 + (i % 2) * 20 + 25, 24000 + (i % 2) * 20, 24000 + (i % 2) * 20 + 20)
            for i in range(20)
        ]
        flat_candles = [
            create_candle(
                1000 + (20 + i) * 60000,
                24010.0 + (1.0 if i % 2 == 0 else -1.0),
                24012.0,
                24008.0,
                24010.0 - (1.0 if i % 2 == 0 else -1.0),
            )
            for i in range(20)
        ]
        candles = wide_candles + flat_candles
        res = self.engine.compute(candles)

        assert res.compression_score >= 0.70
        assert res.zone in (CompressionZone.ARMED, CompressionZone.EXTREME)

    def test_uncompressed_on_strong_trend(self):
        # 40 bars of aggressive 15-point per bar trend
        candles = generate_trending_candles(40, base_price=24000.0, step=15.0)
        res = self.engine.compute(candles)

        assert 0.0 <= res.compression_score <= 1.0
        # Should have low compression score
        assert res.compression_score < 0.55
        assert res.zone == CompressionZone.UNCOMPRESSED
        assert res.displacement_efficiency > 0.70  # Clean displacement

    def test_compression_duration_increment(self):
        candles = generate_flat_candles(35, base_price=24000.0, bar_range=3.0)
        res1 = self.engine.compute(candles, prior_duration=5)
        if res1.compression_score >= 0.55:
            assert res1.duration_bars == 6
        else:
            assert res1.duration_bars == 0

    def test_empty_or_short_series_graceful_fallback(self):
        # Less than atr_long_period (20 bars)
        short_candles = generate_flat_candles(5)
        res = self.engine.compute(short_candles)
        assert res.compression_score == 0.0
        assert res.zone == CompressionZone.UNCOMPRESSED
