"""
Signal Object, TTL, FSM & Distributed Atomicity — §§41,42,43,44,45,46,47,48,49,50
Normalized signal, states, TTL ≤5000ms for fast breakout, repeated TTL checks,
explicit persisted FSM, atomic RISK_APPROVED→EXECUTION_PENDING via CAS or Redis lock,
idempotent execution_intent, reconciliation, final execution guard.
"""
from __future__ import annotations

import time
import uuid
import asyncio
from dataclasses import dataclass, field
from typing import Literal, Any

SignalState = Literal[
    "NO_SETUP", "POSSIBLE", "WATCH", "CONFIRMED", "REJECTED",
    "INVALIDATED", "CONFLICTED", "RISK_REJECTED", "EXPIRED",
]
FSMState = Literal[
    "SIGNAL_CREATED", "AI_PENDING", "AI_CONFIRMED", "AI_REJECTED", "AI_UNCERTAIN",
    "VALIDATED", "RISK_PENDING", "RISK_APPROVED", "RISK_REJECTED",
    "EXECUTION_PENDING", "EXECUTED", "REJECTED", "EXPIRED", "INVALIDATED", "CANCELLED", "FAILED",
]

# Allowed FSM transitions
FSM_TRANSITIONS: dict[str, set[str]] = {
    "SIGNAL_CREATED": {"AI_PENDING", "VALIDATED", "REJECTED", "EXPIRED", "INVALIDATED"},
    "AI_PENDING": {"AI_CONFIRMED", "AI_REJECTED", "AI_UNCERTAIN", "EXPIRED", "INVALIDATED"},
    "AI_CONFIRMED": {"VALIDATED", "REJECTED", "EXPIRED", "INVALIDATED"},
    "AI_REJECTED": {"REJECTED", "EXPIRED"},
    "AI_UNCERTAIN": {"VALIDATED", "REJECTED", "EXPIRED"},
    "VALIDATED": {"RISK_PENDING", "REJECTED", "EXPIRED", "INVALIDATED"},
    "RISK_PENDING": {"RISK_APPROVED", "RISK_REJECTED", "EXPIRED", "INVALIDATED"},
    "RISK_APPROVED": {"EXECUTION_PENDING", "EXPIRED", "INVALIDATED", "FAILED"},
    "RISK_REJECTED": {"REJECTED", "FAILED"},
    "EXECUTION_PENDING": {"EXECUTED", "FAILED", "REJECTED", "EXPIRED", "INVALIDATED", "CANCELLED"},
    "EXECUTED": set(),
    "REJECTED": set(),
    "EXPIRED": set(),
    "INVALIDATED": set(),
    "CANCELLED": set(),
    "FAILED": set(),
}


@dataclass
class Signal:
    signal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    instrument_id: str = ""
    strategy: str = "BREAKOUT"
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] = "NEUTRAL"
    market_context_id: str | None = None

    short_horizon: dict[str, Any] = field(default_factory=dict)  # status, confidence, horizon_minutes etc
    continuation: dict[str, Any] = field(default_factory=dict)
    ai: dict[str, Any] = field(default_factory=dict)  # status, confidence etc

    validation_status: str = "PENDING"
    risk_status: str = "PENDING"

    created_at_utc: int = field(default_factory=lambda: int(time.time()*1000))
    expires_at_utc: int = field(default_factory=lambda: int(time.time()*1000) + 5000)
    ttl_ms: int = 5000

    execution_intent_id: str | None = None
    broker_order_id: str | None = None

    fsm_state: FSMState = "SIGNAL_CREATED"
    state_history: list[dict] = field(default_factory=list)
    error: str | None = None

    def is_expired(self, now_ms: int | None = None) -> bool:
        now_ms = now_ms if now_ms is not None else int(time.time()*1000)
        return now_ms > self.expires_at_utc

    def ttl_remaining_ms(self, now_ms: int | None = None) -> int:
        now_ms = now_ms if now_ms is not None else int(time.time()*1000)
        return max(0, self.expires_at_utc - now_ms)

    def to_dict(self) -> dict:
        return {
            "signal_id": self.signal_id,
            "instrument_id": self.instrument_id,
            "strategy": self.strategy,
            "direction": self.direction,
            "market_context_id": self.market_context_id,
            "short_horizon": self.short_horizon,
            "continuation": self.continuation,
            "ai": self.ai,
            "validation_status": self.validation_status,
            "risk_status": self.risk_status,
            "created_at_utc": self.created_at_utc,
            "expires_at_utc": self.expires_at_utc,
            "ttl_ms": self.ttl_ms,
            "execution_intent_id": self.execution_intent_id,
            "broker_order_id": self.broker_order_id,
            "fsm_state": self.fsm_state,
            "error": self.error,
        }


def create_signal(
    instrument_id: str,
    strategy: str = "BREAKOUT",
    direction: Literal["BULLISH","BEARISH","NEUTRAL"] = "NEUTRAL",
    market_context_id: str | None = None,
    short_horizon: dict | None = None,
    continuation: dict | None = None,
    ai: dict | None = None,
    ttl_ms: int = 5000,
) -> Signal:
    now_ms = int(time.time()*1000)
    sig = Signal(
        signal_id=str(uuid.uuid4()),
        instrument_id=instrument_id.upper(),
        strategy=strategy,
        direction=direction,
        market_context_id=market_context_id,
        short_horizon=short_horizon or {},
        continuation=continuation or {},
        ai=ai or {},
        created_at_utc=now_ms,
        expires_at_utc=now_ms + ttl_ms,
        ttl_ms=ttl_ms,
        fsm_state="SIGNAL_CREATED",
    )
    sig.state_history.append({"state": "SIGNAL_CREATED", "at_ms": now_ms})
    return sig


# ── TTL Checks (§44 — repeated at every stage) ────────────────────────
def check_ttl(signal: Signal, stage: str, now_ms: int | None = None) -> tuple[bool, str | None]:
    """
    Returns (is_valid, error). If expired → SIGNAL → EXPIRED, no execution permitted.
    Called at: AI completion, validation, risk approval, execution intent creation,
    order construction, immediately before broker submission.
    """
    if signal.is_expired(now_ms):
        signal.fsm_state = "EXPIRED"  # type: ignore
        signal.error = f"SIGNAL_EXPIRED at {stage} ttl exceeded"
        return False, signal.error
    return True, None


# ── FSM Transitions ───────────────────────────────────────────────────
class SignalFSM:
    def __init__(self):
        self._signals: dict[str, Signal] = {}
        self._lock = asyncio.Lock()  # in-process guard; production needs DB CAS / Redis
        # For atomicity simulation: also support DB-like compare-and-swap in memory

    def register(self, sig: Signal) -> None:
        self._signals[sig.signal_id] = sig

    def get(self, signal_id: str) -> Signal | None:
        return self._signals.get(signal_id)

    def transition(self, signal_id: str, to_state: FSMState, now_ms: int | None = None) -> tuple[bool, str | None]:
        sig = self._signals.get(signal_id)
        if not sig:
            return False, "signal not found"
        if sig.fsm_state == to_state:
            return True, None
        # Check TTL first — expired cannot transition to EXECUTION_PENDING etc.
        if sig.is_expired(now_ms) and to_state not in ("EXPIRED", "INVALIDATED", "FAILED", "CANCELLED"):
            sig.fsm_state = "EXPIRED"  # type: ignore
            return False, "SIGNAL_EXPIRED"
        allowed = FSM_TRANSITIONS.get(sig.fsm_state, set())
        if to_state not in allowed:
            return False, f"illegal transition {sig.fsm_state} → {to_state}"
        sig.fsm_state = to_state  # type: ignore
        sig.state_history.append({"state": to_state, "at_ms": int(time.time()*1000) if now_ms is None else now_ms})
        return True, None

    # ── Distributed atomicity — CAS preferred (§47) ──────────────────
    def cas_to_execution_pending(self, signal_id: str, now_ms: int | None = None) -> tuple[bool, str | None]:
        """
        Atomic RISK_APPROVED → EXECUTION_PENDING
        In production:
        UPDATE signals SET state='EXECUTION_PENDING' WHERE signal_id=:id AND state='RISK_APPROVED' AND expires_at_utc > :now AND execution_intent_id IS NULL
        require affected_rows == 1
        Here we simulate with lock + check.
        """
        # Use synchronous fallback if no event loop
        sig = self._signals.get(signal_id)
        if not sig:
            return False, "signal not found"
        if sig.fsm_state != "RISK_APPROVED":
            return False, f"CAS_FAILED: expected RISK_APPROVED got {sig.fsm_state}"
        if sig.is_expired(now_ms):
            sig.fsm_state = "EXPIRED"  # type: ignore
            return False, "SIGNAL_EXPIRED"
        if sig.execution_intent_id is not None:
            return False, "CAS_FAILED: execution_intent_id already set (duplicate intent)"
        # Simulate CAS success
        sig.fsm_state = "EXECUTION_PENDING"  # type: ignore
        sig.execution_intent_id = str(uuid.uuid4())
        sig.state_history.append({"state": "EXECUTION_PENDING", "at_ms": int(time.time()*1000) if now_ms is None else now_ms, "execution_intent_id": sig.execution_intent_id})
        return True, None

    async def cas_to_execution_pending_async(self, signal_id: str, now_ms: int | None = None) -> tuple[bool, str | None]:
        async with self._lock:
            return self.cas_to_execution_pending(signal_id, now_ms)


signal_fsm = SignalFSM()


# ── Price / Market Freshness §45 — TTL is not sufficient ─────────────
@dataclass
class FreshnessCheck:
    passed: bool
    reason: str | None = None
    details: dict | None = None


def check_freshness_before_submit(
    signal: Signal,
    latest_price: Any | None,
    signal_price: Any | None,
    max_slippage_pct: float = 0.5,
    market_session_state: str = "OPEN",
    feed_health: str = "HEALTHY",
    risk_approved: bool = True,
    contract_valid: bool = True,
    invalidation_triggered: bool = False,
) -> FreshnessCheck:
    from app.algo.money import D
    if signal.is_expired():
        return FreshnessCheck(passed=False, reason="SIGNAL_EXPIRED", details={"signal_id": signal.signal_id})
    if feed_health == "FEED_DEGRADED":
        return FreshnessCheck(passed=False, reason="FEED_DEGRADED", details={})
    if market_session_state != "OPEN":
        return FreshnessCheck(passed=False, reason=f"MARKET_SESSION_{market_session_state}", details={})
    if not risk_approved:
        return FreshnessCheck(passed=False, reason="RISK_NOT_APPROVED")
    if not contract_valid:
        return FreshnessCheck(passed=False, reason="CONTRACT_SPEC_MISSING")
    if invalidation_triggered:
        return FreshnessCheck(passed=False, reason="SIGNAL_INVALIDATED breakout no longer valid")
    # Slippage check
    if latest_price is not None and signal_price is not None:
        try:
            lp = D(latest_price); sp = D(signal_price)
            if sp != D(0):
                slip_pct = abs(lp - sp) / sp * D(100)
                if slip_pct > D(max_slippage_pct):
                    return FreshnessCheck(passed=False, reason=f"SLIPPAGE_EXCEEDED {slip_pct:.2f}% > {max_slippage_pct}%", details={"latest": str(lp), "signal_price": str(sp)})
        except Exception:
            pass
    return FreshnessCheck(passed=True)


# ── Final Execution Guard §50 — 12 checks immediately before broker submission ─
def final_execution_guard(
    signal: Signal,
    execution_intent_id: str | None,
    latest_price: Any | None = None,
    feed_health: str = "HEALTHY",
    market_session_state: str = "OPEN",
    contract_spec: dict | None = None,
    order_quantity: Any | None = None,
    order_price: Any | None = None,
    slippage_pct: float | None = None,
    max_slippage_pct: float = 0.5,
    risk_approved: bool = True,
    has_duplicate_order: bool = False,
    setup_invalidated: bool = False,
) -> tuple[bool, str | None]:
    checks = []
    # 1. Signal state
    if signal.fsm_state != "EXECUTION_PENDING":
        return False, f"GUARD_FAIL signal state {signal.fsm_state} != EXECUTION_PENDING"
    # 2. Execution-intent ownership
    if execution_intent_id is None or signal.execution_intent_id != execution_intent_id:
        return False, "GUARD_FAIL execution_intent ownership mismatch"
    # 3. TTL
    if signal.is_expired():
        signal.fsm_state = "EXPIRED"  # type: ignore
        return False, "GUARD_FAIL SIGNAL_EXPIRED"
    # 4. Feed health
    if feed_health == "FEED_DEGRADED":
        return False, "GUARD_FAIL FEED_DEGRADED"
    # 5. Market session
    if market_session_state != "OPEN":
        return False, f"GUARD_FAIL market session {market_session_state}"
    # 6. Current price / slippage
    if latest_price is not None and order_price is not None:
        from app.algo.money import D
        try:
            slip = abs(D(latest_price) - D(order_price)) / D(order_price) * D(100) if D(order_price) != D(0) else D(0)
            if slip > D(max_slippage_pct):
                return False, f"GUARD_FAIL slippage {slip:.2f}% > {max_slippage_pct}%"
        except Exception:
            pass
    # 7. Slippage permitted check already above
    # 8. Contract spec
    if contract_spec is None:
        return False, "GUARD_FAIL CONTRACT_SPEC_MISSING"
    # 9. Quantity/tick validity
    if contract_spec and order_quantity is not None and order_price is not None:
        from app.institutional.decimal_types import validate_quantity, normalize_price_to_tick
        try:
            mn = contract_spec.get("min_order_qty", "1")
            step = contract_spec.get("quantity_step", "1")
            lot = contract_spec.get("lot_size")
            ok, reason = validate_quantity(order_quantity, mn, step, lot)
            if not ok:
                return False, f"GUARD_FAIL {reason}"
            # Tick validation
            tick = contract_spec.get("tick_size", "0.05")
            quantized = normalize_price_to_tick(order_price, tick)
            from app.algo.money import D
            if D(quantized) != D(order_price):
                return False, f"GUARD_FAIL price not tick-aligned: {order_price} vs quantized {quantized}"
        except Exception as e:
            return False, f"GUARD_FAIL contract validation error: {e}"
    # 10. Risk approval
    if not risk_approved:
        return False, "GUARD_FAIL RISK_NOT_APPROVED"
    # 11. No duplicate order
    if has_duplicate_order:
        return False, "GUARD_FAIL duplicate order detected"
    # 12. Setup not invalidated
    if setup_invalidated:
        return False, "GUARD_FAIL setup invalidated"
    return True, None


# ── Broker Reconciliation helper §49 ─────────────────────────────────
@dataclass
class ReconciliationState:
    status: Literal["RECONCILIATION_REQUIRED", "RECONCILED", "UNKNOWN"]
    reason: str | None = None


def needs_reconciliation(broker_response: dict | None, error: str | None = None) -> ReconciliationState:
    if broker_response is None or broker_response.get("status") == "UNKNOWN" or error in ("BROKER_TIMEOUT", "API_ERROR", "AMBIGUOUS"):
        return ReconciliationState(status="RECONCILIATION_REQUIRED", reason=error or "ambiguous broker response")
    return ReconciliationState(status="RECONCILED")
