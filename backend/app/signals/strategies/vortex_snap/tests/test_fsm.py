"""
Unit tests for 16-State Finite State Machine (§16).
"""
import pytest
from app.signals.strategies.vortex_snap.feature_engine import VortexFeatureEngine
from app.signals.strategies.vortex_snap.signals.state_machine import VortexSnapFSM
from app.signals.strategies.vortex_snap.types import CompressionZone, VortexState
from app.signals.strategies.vortex_snap.tests.conftest import create_candle, generate_flat_candles


class TestVortexSnapFSM:
    def setup_method(self):
        self.fsm = VortexSnapFSM(armed_timeout_bars=5)
        self.feature_engine = VortexFeatureEngine()

    def test_idle_to_compression_transition(self):
        assert self.fsm.state == VortexState.IDLE
        candles = generate_flat_candles(30)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)

        state = self.fsm.step(snapshot, candles)
        assert state in (VortexState.COMPRESSION, VortexState.ARMED)
        assert len(self.fsm.transition_history) >= 1

    def test_armed_timeout_returns_to_idle(self):
        # Force state to ARMED
        self.fsm.transition_to(VortexState.ARMED, 1000, "Manual arm")
        candles = generate_flat_candles(30)
        snapshot = self.feature_engine.compute_snapshot("NIFTY", candles)
        snapshot.vacuum.is_vacuum_detected = False
        snapshot.vacuum.range_expansion = 1.0

        # Step until timeout
        for _ in range(6):
            self.fsm.step(snapshot, candles)

        assert self.fsm.state == VortexState.IDLE

    def test_full_lifecycle_continuation(self):
        ts = 1000000
        self.fsm.transition_to(VortexState.PRE_TRADE_VALIDATION, ts, "Validated")
        candles = [create_candle(ts, 24000, 24010, 23995, 24005)]
        snapshot = self.feature_engine.compute_snapshot("NIFTY", generate_flat_candles(25))

        state1 = self.fsm.step(snapshot, candles)
        assert state1 == VortexState.EXECUTABLE

        state2 = self.fsm.step(snapshot, candles)
        assert state2 == VortexState.ACTIVE

        # Advance active state to exit
        for _ in range(10):
            self.fsm.step(snapshot, candles)
        assert self.fsm.state == VortexState.EXIT
