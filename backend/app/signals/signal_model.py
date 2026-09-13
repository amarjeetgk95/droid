"""
Domain Models for Signal Module Decomposition (Phase 2)
Provides structured, typed domain models representing distinct concerns:
  - SignalDefinition (immutable strategy decision)
  - RiskSizing (capital allocation & limits)
  - ConfluenceBreakdown (multi-domain score attribution)
  - ExecutionState (lifecycle & broker fill tracking)
  - SignalOutcome (realized financial metrics & attribution)
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, Field


SignalFSMState = Literal[
    "DETECTED",
    "VALIDATED",
    "ARMED",
    "TRIGGERED",
    "CONFIRMED",
    "TARGET_1_HIT",
    "TARGET_2_HIT",
    "STOP_LOSS_HIT",
    "TIME_STOP_HIT",
    "RUNNER_TIME_STOP_HIT",
    "INVALIDATED",
    "EXPIRED",
    "CLOSED",
]


class ConfluenceBreakdown(BaseModel):
    """Structured, typed confluence breakdown across all quantitative and intelligence domains."""
    technical: float = 50.0
    mtf: float = 50.0
    fno: float = 50.0
    regime: float = 50.0
    ai: float | None = None
    ai_status: str = "UNAVAILABLE"
    ml_score: float | None = None
    ml_status: str = "UNAVAILABLE"
    event_state: str = "NORMAL"
    event_sizing_multiplier: float = 1.0
    fno_degraded: bool = False
    institutional_delta: float = 0.0
    institutional_applied: bool = False
    institutional_reasons: list[str] = Field(default_factory=list)
    institutional_event_date: str | None = None
    institutional_downgrade: bool = False
    institutional_composite: float | None = None
    institutional_composite_sentiment: str | None = None
    institutional_composite_status: str | None = None


class SignalDefinition(BaseModel):
    """
    Immutable Strategy Proposal:
    Represents what the quantitative strategy and scanner decided at creation time.
    These fields must NEVER mutate across lifecycle transitions.
    """
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    underlying: str
    strategy: str
    direction: str
    timeframe: str
    spot_price: Decimal
    entry_min: Decimal
    entry_max: Decimal
    trigger: Decimal
    stop_loss: Decimal
    target_1: Decimal
    target_2: Decimal
    risk_points: Decimal
    risk_reward_t1: float
    risk_reward_t2: float
    confidence: float
    signal_type: str = "INTRADAY"
    is_scalp: bool = False
    ttl_seconds: int = 300
    strategy_version: int = 1
    scoring_version: int = 1
    feature_version: int = 1
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))


class RiskSizing(BaseModel):
    """Risk & position limits calculated by the Central Risk Engine."""
    lots: int | None = None
    quantity: int | None = None
    max_rupee_loss: float | None = None
    risk_r: Decimal | None = None


class ExecutionState(BaseModel):
    """Mutable execution and fill reconciliation state."""
    fsm_state: SignalFSMState = "DETECTED"
    initial_stop_loss: Decimal | None = None
    current_stop_loss: Decimal | None = None
    breakeven_activated: bool = False
    breakeven_trigger_price: Decimal | None = None
    breakeven_activation_price: Decimal | None = None
    time_stop_seconds: int | None = None
    time_stop_at_utc: int | None = None
    runner_time_stop_at_utc: int | None = None
    runner_ttl_seconds: int | None = None
    entry_price: Decimal | None = None
    actual_fill_price: Decimal | None = None
    remaining_qty: Decimal = Decimal(0)
    intended_qty: Decimal = Decimal(0)
    t1_price: Decimal | None = None
    t2_price: Decimal | None = None
    t1_hit: bool = False
    t1_fill_timestamp: int | None = None
    t2_hit: bool = False
    paper_order: dict[str, Any] | None = None
    last_updated_utc: int = Field(default_factory=lambda: int(time.time() * 1000))


class SignalOutcome(BaseModel):
    """Realized financial outcome calculated at exit or milestone."""
    exit_price: Decimal | None = None
    realized_rr: float | None = None
    realized_rr_gross: float | None = None
    realized_rr_net: float | None = None
    cost_breakdown_r: dict[str, Any] | None = None
    terminal_outcome: str | None = None
    outcome_status: str | None = None
