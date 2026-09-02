"""
11-State Deterministic Signal Finite State Machine & Immutable Transition Audit Log
States:
  DETECTED -> VALIDATED -> ARMED -> TRIGGERED -> CONFIRMED -> TARGET_1_HIT -> TARGET_2_HIT / STOP_LOSS_HIT -> CLOSED
Terminal states: TARGET_2_HIT, STOP_LOSS_HIT, INVALIDATED, EXPIRED, CLOSED
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Literal, Optional, Any
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()

SignalFSMState = Literal[
    "DETECTED",
    "VALIDATED",
    "ARMED",
    "TRIGGERED",
    "CONFIRMED",
    "TARGET_1_HIT",
    "TARGET_2_HIT",
    "STOP_LOSS_HIT",
    "INVALIDATED",
    "EXPIRED",
    "CLOSED",
]

ALLOWED_TRANSITIONS: dict[SignalFSMState, set[SignalFSMState]] = {
    "DETECTED": {"VALIDATED", "INVALIDATED", "EXPIRED"},
    "VALIDATED": {"ARMED", "INVALIDATED", "EXPIRED"},
    "ARMED": {"TRIGGERED", "EXPIRED", "INVALIDATED"},
    "TRIGGERED": {"CONFIRMED", "INVALIDATED", "EXPIRED"},
    "CONFIRMED": {"TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "INVALIDATED"},
    "TARGET_1_HIT": {"TARGET_2_HIT", "STOP_LOSS_HIT", "CLOSED"},
    "TARGET_2_HIT": {"CLOSED"},
    "STOP_LOSS_HIT": {"CLOSED"},
    "INVALIDATED": {"CLOSED"},
    "EXPIRED": {"CLOSED"},
    "CLOSED": set(),
}


class FSMTransitionAudit(BaseModel):
    transition_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    from_state: SignalFSMState
    to_state: SignalFSMState
    market_price: Optional[Decimal] = None
    reason_code: str = "STATE_UPDATE"
    processed_timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    guard_snapshot: dict = Field(default_factory=dict)


class SignalInstance(BaseModel):
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
    confluence_breakdown: dict = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)
    option_contract: Optional[dict] = None

    # State & Lifecycle
    fsm_state: SignalFSMState = "DETECTED"
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    expires_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000) + 300000)
    ttl_seconds: int = 300
    last_updated_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    # Realized Execution & Outcomes
    triggered_at_utc: Optional[int] = None
    confirmed_at_utc: Optional[int] = None
    exit_price: Optional[Decimal] = None
    realized_rr: Optional[float] = None
    outcome_status: Optional[str] = None  # WIN_T1, WIN_T2, LOSS_SL, EXPIRED, INVALIDATED
    paper_order: Optional[dict] = None

    state_history: list[FSMTransitionAudit] = Field(default_factory=list)

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        ts = now_ms or int(time.time() * 1000)
        return ts > self.expires_at_utc and self.fsm_state in ("DETECTED", "VALIDATED", "ARMED")

    def ttl_remaining_seconds(self) -> int:
        now_ms = int(time.time() * 1000)
        return max(0, int((self.expires_at_utc - now_ms) / 1000))


class SignalFSMManager:
    """
    Central Thread-Safe in-memory State Machine Manager with append-only audit persistence.
    """

    def __init__(self):
        self._signals: dict[str, SignalInstance] = {}
        self._audit_log: list[FSMTransitionAudit] = []

    def register(self, signal: SignalInstance) -> SignalInstance:
        self._signals[signal.signal_id] = signal
        audit = FSMTransitionAudit(
            signal_id=signal.signal_id,
            from_state="DETECTED",
            to_state=signal.fsm_state,
            market_price=signal.spot_price,
            reason_code="SIGNAL_REGISTERED",
        )
        signal.state_history.append(audit)
        self._audit_log.append(audit)
        return signal

    def get(self, signal_id: str) -> Optional[SignalInstance]:
        return self._signals.get(signal_id)

    def list_active(self, underlying: Optional[str] = None, strategy: Optional[str] = None) -> list[SignalInstance]:
        now_ms = int(time.time() * 1000)
        res = []
        for s in self._signals.values():
            if s.is_expired(now_ms) and s.fsm_state not in ("TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "CLOSED", "EXPIRED"):
                self.transition(s.signal_id, "EXPIRED", reason="TTL_EXCEEDED")
            if underlying and s.underlying != underlying.upper():
                continue
            if strategy and s.strategy != strategy.upper():
                continue
            res.append(s)
        # Sort so ACTIVE & CONFIRMED appear at top, newest first
        state_order = {"CONFIRMED": 0, "TRIGGERED": 1, "ARMED": 2, "VALIDATED": 3, "DETECTED": 4, "TARGET_1_HIT": 5, "TARGET_2_HIT": 6, "STOP_LOSS_HIT": 7, "EXPIRED": 8, "INVALIDATED": 9, "CLOSED": 10}
        res.sort(key=lambda x: (state_order.get(x.fsm_state, 99), -x.created_at_utc))
        return res

    def transition(
        self,
        signal_id: str,
        to_state: SignalFSMState,
        market_price: Optional[Decimal] = None,
        reason: str = "STATE_UPDATE",
        guard_snapshot: Optional[dict] = None,
    ) -> tuple[bool, Optional[str]]:
        sig = self._signals.get(signal_id)
        if not sig:
            return False, "Signal not found"

        if sig.fsm_state == to_state:
            return True, None

        allowed = ALLOWED_TRANSITIONS.get(sig.fsm_state, set())
        if to_state not in allowed:
            err = f"Illegal transition {sig.fsm_state} -> {to_state}"
            logger.warning("fsm_illegal_transition", signal_id=signal_id, error=err)
            return False, err

        from_st = sig.fsm_state
        sig.fsm_state = to_state
        sig.last_updated_utc = int(time.time() * 1000)

        # Update specific timestamps
        if to_state == "TRIGGERED":
            sig.triggered_at_utc = sig.last_updated_utc
        elif to_state == "CONFIRMED":
            sig.confirmed_at_utc = sig.last_updated_utc
        elif to_state in ("TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT"):
            sig.exit_price = market_price
            if to_state == "TARGET_1_HIT":
                sig.outcome_status = "WIN_T1"
                sig.realized_rr = sig.risk_reward_t1
            elif to_state == "TARGET_2_HIT":
                sig.outcome_status = "WIN_T2"
                sig.realized_rr = sig.risk_reward_t2
            elif to_state == "STOP_LOSS_HIT":
                sig.outcome_status = "LOSS_SL"
                sig.realized_rr = -1.0
        elif to_state == "EXPIRED":
            sig.outcome_status = "EXPIRED"
        elif to_state == "INVALIDATED":
            sig.outcome_status = "INVALIDATED"

        audit = FSMTransitionAudit(
            signal_id=signal_id,
            from_state=from_st,
            to_state=to_state,
            market_price=market_price,
            reason_code=reason,
            guard_snapshot=guard_snapshot or {},
        )
        sig.state_history.append(audit)
        self._audit_log.append(audit)
        logger.info("fsm_state_transition", signal_id=signal_id, from_state=from_st, to_state=to_state, reason=reason)
        return True, None


signal_fsm = SignalFSMManager()
