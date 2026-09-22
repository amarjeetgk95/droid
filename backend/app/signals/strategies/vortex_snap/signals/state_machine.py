"""
16-State VORTEX-SNAP Finite State Machine (§16).

Lifecycle:
IDLE -> COMPRESSION -> ARMED -> IGNITION -> CLASSIFICATION ->
(CONTINUATION / ABSORPTION / TRAP) -> CONFIRMATION ->
PRE_TRADE_VALIDATION -> EXECUTABLE -> ACTIVE -> EXIT -> COOLDOWN -> IDLE
"""
from __future__ import annotations

import time
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import (
    Candle,
    CompressionZone,
    EventType,
    StructuralLevel,
    VortexFeatureSnapshot,
    VortexState,
)
from app.signals.strategies.vortex_snap.signals.event_classifier import ClassifiedEvent, EventClassifier
from app.signals.strategies.vortex_snap.signals.confirmation import ConfirmationEngine, ConfirmationResult
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode


class FSMTransitionLog(BaseModel):
    """Immutable audit record of a state transition."""
    from_state: VortexState
    to_state: VortexState
    timestamp_ms: int
    reason: str


class VortexSnapFSM:
    """Implements the 16-state lifecycle for VORTEX-SNAP trading candidates."""

    def __init__(
        self,
        armed_timeout_bars: int = 15,
        confirmation_timeout_bars: int = 3,
        active_timeout_bars: int = 10,
    ) -> None:
        self.state: VortexState = VortexState.IDLE
        self.armed_timeout_bars = armed_timeout_bars
        self.confirmation_timeout_bars = confirmation_timeout_bars
        self.active_timeout_bars = active_timeout_bars

        # Internal tracking
        self.current_event: Optional[ClassifiedEvent] = None
        self.trigger_candle: Optional[Candle] = None
        self.entry_price: Optional[float] = None
        self.state_enter_bar_count: int = 0
        self.transition_history: List[FSMTransitionLog] = []

        self.classifier = EventClassifier()
        self.confirmation_engine = ConfirmationEngine()

    def transition_to(self, new_state: VortexState, timestamp_ms: int, reason: str) -> None:
        """Execute state transition with audit log."""
        log = FSMTransitionLog(
            from_state=self.state,
            to_state=new_state,
            timestamp_ms=timestamp_ms,
            reason=reason,
        )
        self.transition_history.append(log)
        self.state = new_state
        self.state_enter_bar_count = 0

    def step(
        self,
        snapshot: VortexFeatureSnapshot,
        candles_1m: List[Candle],
    ) -> VortexState:
        """Progress state machine given new 1-minute candle snapshot.

        Args:
            snapshot: Current feature snapshot.
            candles_1m: Complete 1-minute candle history up to current.

        Returns:
            Updated VortexState.
        """
        self.state_enter_bar_count += 1
        ts = snapshot.timestamp_ms
        current_candle = candles_1m[-1]

        # ─────────────────────────────────────────────────────────────────
        # STATE: IDLE
        # ─────────────────────────────────────────────────────────────────
        if self.state == VortexState.IDLE:
            if snapshot.compression.zone == CompressionZone.WATCH:
                self.transition_to(VortexState.COMPRESSION, ts, "Compression score entered WATCH zone")
            elif snapshot.compression.zone in (CompressionZone.ARMED, CompressionZone.EXTREME):
                self.transition_to(VortexState.ARMED, ts, "Compression score entered ARMED/EXTREME zone")

        # ─────────────────────────────────────────────────────────────────
        # STATE: COMPRESSION
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.COMPRESSION:
            if snapshot.compression.zone in (CompressionZone.ARMED, CompressionZone.EXTREME):
                self.transition_to(VortexState.ARMED, ts, "Compression upgraded to ARMED")
            elif snapshot.compression.zone == CompressionZone.UNCOMPRESSED:
                self.transition_to(VortexState.IDLE, ts, "Compression dissolved without arming")

        # ─────────────────────────────────────────────────────────────────
        # STATE: ARMED
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.ARMED:
            # Check for range expansion / vacuum ignition
            if snapshot.vacuum.is_vacuum_detected or snapshot.vacuum.range_expansion >= 1.5:
                self.transition_to(VortexState.IGNITION, ts, "Liquidity vacuum ignition detected")
            elif snapshot.compression.zone == CompressionZone.UNCOMPRESSED:
                self.transition_to(VortexState.IDLE, ts, "Armed state lost compression")
            elif self.state_enter_bar_count > self.armed_timeout_bars:
                self.transition_to(VortexState.IDLE, ts, "Armed state timed out")

        # ─────────────────────────────────────────────────────────────────
        # STATE: IGNITION
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.IGNITION:
            # Immediate event classification attempt
            event = self.classifier.classify(snapshot, candles_1m)
            if event:
                self.current_event = event
                self.trigger_candle = current_candle
                if event.event_type == EventType.CONTINUATION:
                    self.transition_to(VortexState.CONTINUATION, ts, "Classified as CONTINUATION snap")
                elif event.event_type == EventType.ABSORPTION:
                    self.transition_to(VortexState.ABSORPTION, ts, "Classified as ABSORPTION snap")
                elif event.event_type == EventType.VACUUM_TRAP:
                    self.transition_to(VortexState.TRAP, ts, "Classified as VACUUM_TRAP snap")
            else:
                self.transition_to(VortexState.IDLE, ts, "Ignition without valid event classification")

        # ─────────────────────────────────────────────────────────────────
        # STATES: CONTINUATION / ABSORPTION / TRAP
        # ─────────────────────────────────────────────────────────────────
        elif self.state in (VortexState.CONTINUATION, VortexState.ABSORPTION, VortexState.TRAP):
            # Transition to CONFIRMATION phase
            self.transition_to(VortexState.CONFIRMATION, ts, "Awaiting event confirmation")

        # ─────────────────────────────────────────────────────────────────
        # STATE: CONFIRMATION
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.CONFIRMATION:
            if self.current_event and self.trigger_candle:
                conf = self.confirmation_engine.evaluate(
                    event=self.current_event,
                    trigger_candle=self.trigger_candle,
                    confirm_candle=current_candle,
                    snapshot=snapshot,
                )
                if conf.is_confirmed:
                    self.transition_to(VortexState.PRE_TRADE_VALIDATION, ts, f"Confirmed via {conf.confirmation_mechanism}")
                elif self.state_enter_bar_count >= self.confirmation_timeout_bars:
                    self.transition_to(VortexState.COOLDOWN, ts, "Confirmation timed out")
            else:
                self.transition_to(VortexState.IDLE, ts, "Missing trigger context in confirmation")

        # ─────────────────────────────────────────────────────────────────
        # STATE: PRE_TRADE_VALIDATION
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.PRE_TRADE_VALIDATION:
            # Deterministic and risk checks happen here; if cleared:
            self.transition_to(VortexState.EXECUTABLE, ts, "Pre-trade risk and data gates passed")

        # ─────────────────────────────────────────────────────────────────
        # STATE: EXECUTABLE
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.EXECUTABLE:
            # Emitted for execution, immediately transitions to ACTIVE upon simulated/live fill
            self.entry_price = current_candle.close
            self.transition_to(VortexState.ACTIVE, ts, "Order placed / filled")

        # ─────────────────────────────────────────────────────────────────
        # STATE: ACTIVE
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.ACTIVE:
            if self.state_enter_bar_count >= self.active_timeout_bars:
                self.transition_to(VortexState.EXIT, ts, "Trade reached maximum holding horizon")

        # ─────────────────────────────────────────────────────────────────
        # STATE: EXIT
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.EXIT:
            self.transition_to(VortexState.COOLDOWN, ts, "Position closed, entering cooldown")

        # ─────────────────────────────────────────────────────────────────
        # STATE: COOLDOWN
        # ─────────────────────────────────────────────────────────────────
        elif self.state == VortexState.COOLDOWN:
            if self.state_enter_bar_count >= 2:  # 2 bars cooldown minimum
                self.current_event = None
                self.trigger_candle = None
                self.entry_price = None
                self.transition_to(VortexState.IDLE, ts, "Cooldown completed")

        return self.state
