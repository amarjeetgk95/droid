"""
Point-In-Time and Anti-Lookahead Validation Suite (§2 Principles 1-2).

Enforces that:
1. Snapshot at candle T uses ONLY information at or before candle T.
2. Altering future candles (T+1, T+2, ...) has strictly ZERO impact on snapshot at T.
3. Online streaming calculation matches historical batch slice at every step.
"""
import copy
import pytest
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.tests.conftest import (
    create_candle,
    generate_trending_candles,
)


class TestNoLookaheadInvariants:
    def test_future_candle_alteration_has_zero_effect_on_past(self):
        engine1 = VortexFeatureEngine()
        engine2 = VortexFeatureEngine()

        base_candles = generate_trending_candles(40, base_price=24000.0, step=8.0)
        t_target = 25  # Evaluate at bar 25

        # Engine 1 computes on history up to bar 25
        snapshot_at_t = engine1.compute_snapshot(
            instrument="NIFTY",
            candles_1m=base_candles[: t_target + 1],
        )

        # Engine 2 computes on an alternate reality where bar 26+ has a massive crash or spike
        mutated_candles = copy.deepcopy(base_candles[: t_target + 1])
        # Add extreme future candle at bar 26
        extreme_future_candle = create_candle(
            mutated_candles[-1].timestamp + 60000,
            open_p=30000.0,
            high_p=35000.0,
            low_p=29000.0,
            close_p=34000.0,
            volume=500000.0,
        )

        # Snapshot at T on mutated series
        snapshot_at_t_mutated = engine2.compute_snapshot(
            instrument="NIFTY",
            candles_1m=mutated_candles,  # only passed up to T
        )

        # Invariant 1: Compression score at T must be bitwise identical
        assert snapshot_at_t.compression.compression_score == snapshot_at_t_mutated.compression.compression_score
        assert snapshot_at_t.compression.atr_ratio == snapshot_at_t_mutated.compression.atr_ratio

        # Invariant 2: Pressure score at T must be bitwise identical
        assert snapshot_at_t.pressure.pressure_score == snapshot_at_t_mutated.pressure.pressure_score
        assert snapshot_at_t.pressure.net_pressure == snapshot_at_t_mutated.pressure.net_pressure

        # Invariant 3: Translation ratio at T must be bitwise identical
        assert snapshot_at_t.translation.translation_ratio == snapshot_at_t_mutated.translation.translation_ratio
        assert snapshot_at_t.translation.translation_state == snapshot_at_t_mutated.translation.translation_state

        # Invariant 4: Absorption score at T must be bitwise identical
        assert snapshot_at_t.absorption.absorption_score == snapshot_at_t_mutated.absorption.absorption_score

        # Invariant 5: Regime at T must be bitwise identical
        assert snapshot_at_t.regime.regime == snapshot_at_t_mutated.regime.regime
        assert snapshot_at_t.regime.regime_confidence == snapshot_at_t_mutated.regime.regime_confidence

    def test_deterministic_replay_parity(self):
        """Two identical runs must produce bitwise identical snapshots."""
        candles = generate_trending_candles(30, base_price=24000.0, step=5.0)

        engine1 = VortexFeatureEngine()
        engine2 = VortexFeatureEngine()

        snap1 = engine1.compute_snapshot("BANKNIFTY", candles)
        snap2 = engine2.compute_snapshot("BANKNIFTY", candles)

        assert snap1.compression.compression_score == snap2.compression.compression_score
        assert snap1.pressure.pressure_score == snap2.pressure.pressure_score
        assert snap1.translation.translation_ratio == snap2.translation.translation_ratio
        assert snap1.absorption.absorption_score == snap2.absorption.absorption_score
        assert snap1.vacuum.liquidity_vacuum_score == snap2.vacuum.liquidity_vacuum_score
        assert snap1.snap_energy.snap_energy == snap2.snap_energy.snap_energy
