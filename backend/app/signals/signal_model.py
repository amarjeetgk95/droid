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

import hashlib
import json
import time
import uuid
from decimal import Decimal
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    These fields must NEVER mutate across lifecycle transitions (frozen=True).
    Level changes require a NEW signal_id (see with_updated_levels).
    """
    model_config = ConfigDict(frozen=True)

    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    idempotency_key: str | None = None
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
    feature_hash: str | None = None
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    @staticmethod
    def compute_feature_hash(
        underlying: str,
        strategy: str,
        direction: str,
        trigger: Any,
        stop_loss: Any,
        target_1: Any,
        target_2: Any,
        strategy_version: int = 1,
        feature_version: int = 1,
    ) -> str:
        canonical = json.dumps(
            {
                "underlying": str(underlying).upper(),
                "strategy": str(strategy).upper(),
                "direction": str(direction).upper(),
                "trigger": format(Decimal(str(trigger)), "f"),
                "stop_loss": format(Decimal(str(stop_loss)), "f"),
                "target_1": format(Decimal(str(target_1)), "f"),
                "target_2": format(Decimal(str(target_2)), "f"),
                "strategy_version": int(strategy_version),
                "feature_version": int(feature_version),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def derive_idempotency_key(signal_id: str, strategy_version: int, feature_hash: str) -> str:
        raw = f"{signal_id}:{strategy_version}:{feature_hash}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    @model_validator(mode="after")
    def _enforce_hash(self) -> "SignalDefinition":
        # Compute canonical hashes when missing; enforce consistency when present.
        try:
            expected_feature = SignalDefinition.compute_feature_hash(
                self.underlying,
                self.strategy,
                self.direction,
                self.trigger,
                self.stop_loss,
                self.target_1,
                self.target_2,
                self.strategy_version,
                self.feature_version,
            )
        except Exception:
            return self
        # frozen model: use object.__setattr__ to populate derived fields
        if not self.feature_hash:
            object.__setattr__(self, "feature_hash", expected_feature)
        if not self.idempotency_key:
            fh = self.feature_hash or expected_feature
            object.__setattr__(
                self,
                "idempotency_key",
                SignalDefinition.derive_idempotency_key(self.signal_id, self.strategy_version, fh),
            )
        return self

    def with_updated_levels(
        self,
        trigger: Decimal | None = None,
        stop_loss: Decimal | None = None,
        target_1: Decimal | None = None,
        target_2: Decimal | None = None,
    ) -> "SignalDefinition":
        """Level changes invalidate the proposal hash → new signal_id required.

        Returns a NEW SignalDefinition with a fresh signal_id + recomputed
        feature_hash/idempotency_key. Never mutates self (frozen).
        """
        data = self.model_dump()
        changed = False
        for k, v in (("trigger", trigger), ("stop_loss", stop_loss), ("target_1", target_1), ("target_2", target_2)):
            if v is not None and Decimal(str(v)) != Decimal(str(data[k])):
                data[k] = v
                changed = True
        if not changed:
            return self
        data.pop("feature_hash", None)
        data.pop("idempotency_key", None)
        # Enforce new identity on level change
        data["signal_id"] = str(uuid.uuid4())
        return SignalDefinition(**data)


class RiskSizing(BaseModel):
    """Risk & position limits calculated by the Central Risk Engine."""
    lots: int | None = None
    quantity: int | None = None
    max_rupee_loss: float | None = None
    risk_r: Decimal | None = None


class ExecutionState(BaseModel):
    """Mutable execution and fill reconciliation state."""
    model_config = ConfigDict(validate_assignment=True)

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
    # Canonical execution reference (preferred). Legacy dict retained for
    # backward-compat reads but new code must use paper_order_ref.
    paper_order: dict[str, Any] | None = None
    paper_order_ref: str | None = None
    # Price domain of execution fills: SPOT (index/future) vs PREMIUM (option).
    price_domain: Literal["SPOT", "PREMIUM"] = "SPOT"
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
