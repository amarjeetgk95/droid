"""
Standard Signal Object for VORTEX-SNAP Scalping Engine (§41).

Complete machine-readable signal contract emitted by the strategy pipeline.
"""
from __future__ import annotations

import uuid
from typing import List, Literal, Optional
from pydantic import BaseModel, Field

from app.signals.strategies.vortex_snap.types import (
    EventType,
    MarketRegime,
    VortexState,
)
from app.signals.strategies.vortex_snap.signals.reason_codes import ReasonCode


class VortexSignal(BaseModel):
    """Machine-readable signal representation (§41)."""
    strategy: str = "VORTEX-SNAP"
    instrument: Literal["NIFTY", "BANKNIFTY", "SENSEX"]
    timestamp: str
    timestamp_ms: int
    direction: Literal["LONG", "SHORT"]
    trade_action: Literal["LONG_CALL", "LONG_PUT"]
    event_type: EventType
    state: VortexState

    # Core microstructure metrics at trigger time
    compression_score: float = Field(ge=0.0, le=1.0)
    pressure_score: float = Field(ge=-1.0, le=1.0)
    translation_score: float = Field(ge=0.0, le=1.0)
    absorption_score: float = Field(ge=0.0, le=1.0)
    liquidity_vacuum_score: float = Field(ge=0.0, le=1.0)
    snap_energy: float = Field(ge=0.0, le=1.0)
    level_relevance: float = Field(ge=0.0, le=1.0)
    regime: MarketRegime

    # Validation & Probability
    ml_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    calibrated_probability: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    signal_confidence: float = Field(ge=0.0, le=1.0)

    # Dynamic Execution & Risk parameters (§20, §21)
    expected_move: float = Field(gt=0.0)
    expected_holding_minutes: float = Field(gt=0.0)
    entry_price: float = Field(gt=0.0)
    stop_price: float = Field(gt=0.0)
    target_1: float = Field(gt=0.0)
    target_2: float = Field(gt=0.0)
    risk_points: float = Field(gt=0.0)
    reward_risk_ratio: float = Field(gt=0.0)

    # Governance & Traceability (§36, §40, §42)
    reason_codes: List[ReasonCode] = Field(default_factory=list)
    data_quality: Literal["PASS", "FAIL"] = "PASS"
    risk_gate: Literal["PASS", "FAIL"] = "PASS"
    event_id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:10]}")
    parent_event_id: Optional[str] = None
    signal_id: str = Field(default_factory=lambda: f"vtx_{uuid.uuid4().hex[:12]}")

    @property
    def is_executable(self) -> bool:
        return (
            self.state == VortexState.EXECUTABLE
            and self.data_quality == "PASS"
            and self.risk_gate == "PASS"
        )
