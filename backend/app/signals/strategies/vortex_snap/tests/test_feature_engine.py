"""
Unit and integration tests for Unified VortexFeatureEngine.
"""
import pytest
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.types import (
    CompressionZone,
    TranslationState,
)
from app.signals.strategies.vortex_snap.tests.conftest import (
    generate_flat_candles,
    generate_trending_candles,
)


class TestVortexFeatureEngine:
    def setup_method(self):
        self.engine = VortexFeatureEngine()

    def test_full_snapshot_computation(self):
        candles = generate_flat_candles(35, base_price=24150.0, bar_range=6.0)
        snapshot = self.engine.compute_snapshot(
            instrument="NIFTY",
            candles_1m=candles,
            pdh=24300.0,
            pdl=24000.0,
            pdc=24100.0,
            cdo=24120.0,
            vwap=24140.0,
        )

        assert snapshot.instrument == "NIFTY"
        assert snapshot.spot_price == candles[-1].close
        assert snapshot.total_latency_ms >= 0.0
        assert snapshot.total_latency_ms < 50.0  # Fast latency target (§49)

        # Verify all sub-results are present and bounded
        assert 0.0 <= snapshot.compression.compression_score <= 1.0
        assert -1.0 <= snapshot.pressure.pressure_score <= 1.0
        assert snapshot.translation.translation_ratio >= 0.0
        assert 0.0 <= snapshot.absorption.absorption_score <= 1.0
        assert 0.0 <= snapshot.vacuum.liquidity_vacuum_score <= 1.0
        assert 0.0 <= snapshot.snap_energy.snap_energy <= 1.0
        assert snapshot.regime.regime_confidence >= 0.0

    def test_ablation_masking(self):
        # Disable compression and pressure to test ablation safety (§32)
        candles = generate_trending_candles(30)
        overrides = {
            "compression": False,
            "pressure": False,
        }
        snapshot = self.engine.compute_snapshot(
            instrument="BANKNIFTY",
            candles_1m=candles,
            ablation_overrides=overrides,
        )

        # Compression should be disabled fallback
        assert snapshot.compression.compression_score == 0.0
        assert snapshot.compression.zone == CompressionZone.UNCOMPRESSED
        # Pressure should be disabled fallback
        assert snapshot.pressure.pressure_score == 0.0
        assert snapshot.ablation_mask["compression"] is False
        assert snapshot.ablation_mask["pressure"] is False
        assert snapshot.ablation_mask["translation"] is True

    def test_reset_state(self):
        candles = generate_flat_candles(25)
        self.engine.compute_snapshot("SENSEX", candles)
        assert self.engine._prior_compression_duration >= 0
        self.engine.reset_state()
        assert self.engine._prior_compression_duration == 0
        assert self.engine._prior_pressure_persistence == 0
        assert len(self.engine._compression_history) == 0
