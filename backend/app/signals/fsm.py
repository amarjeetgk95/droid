"""
11-State Deterministic Signal Finite State Machine & Immutable Transition Audit Log
States:
  DETECTED -> VALIDATED -> ARMED -> TRIGGERED -> CONFIRMED -> TARGET_1_HIT -> TARGET_2_HIT / STOP_LOSS_HIT -> CLOSED
Terminal states: TARGET_2_HIT, STOP_LOSS_HIT, INVALIDATED, EXPIRED, CLOSED
"""
from __future__ import annotations

import time
import uuid
import threading
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field, computed_field
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
    "TIME_STOP_HIT",
    "RUNNER_TIME_STOP_HIT",
    "INVALIDATED",
    "EXPIRED",
    "CLOSED",
]

ALLOWED_TRANSITIONS: dict[SignalFSMState, set[SignalFSMState]] = {
    "DETECTED": {"VALIDATED", "ARMED", "CONFIRMED", "INVALIDATED", "EXPIRED"},
    "VALIDATED": {"ARMED", "TRIGGERED", "CONFIRMED", "INVALIDATED", "EXPIRED"},
    "ARMED": {"TRIGGERED", "CONFIRMED", "EXPIRED", "INVALIDATED"},
    "TRIGGERED": {"CONFIRMED", "INVALIDATED", "EXPIRED"},
    "CONFIRMED": {"TARGET_1_HIT", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "INVALIDATED", "EXPIRED", "CLOSED"},
    "TARGET_1_HIT": {"TARGET_2_HIT", "STOP_LOSS_HIT", "RUNNER_TIME_STOP_HIT", "CLOSED"},
    "TARGET_2_HIT": {"CLOSED"},
    "STOP_LOSS_HIT": {"CLOSED"},
    "TIME_STOP_HIT": {"CLOSED"},
    "RUNNER_TIME_STOP_HIT": {"CLOSED"},
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

    # Version 6.0 Desk & Risk Fields
    signal_type: str = "INTRADAY"  # SCALP, INTRADAY, SWING
    is_scalp: bool = False
    initial_stop_loss: Optional[Decimal] = None
    current_stop_loss: Optional[Decimal] = None
    risk_r: Optional[Decimal] = None

    # Breakeven Ratchet (+0.8R)
    breakeven_activated: bool = False
    breakeven_trigger_price: Optional[Decimal] = None
    breakeven_activation_price: Optional[Decimal] = None

    # Two-Clock Lifecycles (§6, §20)
    time_stop_seconds: Optional[int] = None
    time_stop_at_utc: Optional[int] = None
    runner_time_stop_at_utc: Optional[int] = None
    runner_ttl_seconds: Optional[int] = None

    # Position Sizing & Capital Allocation
    lots: Optional[int] = None
    quantity: Optional[int] = None
    max_rupee_loss: Optional[float] = None

    # Staged Target Execution (§18, §25)
    t1_price: Optional[Decimal] = None
    t2_price: Optional[Decimal] = None
    t1_hit: bool = False
    t1_fill_timestamp: Optional[int] = None
    t2_hit: bool = False

    # Fill Reconciliation & Residual Quantity Tracking (§24, §25)
    entry_price: Optional[Decimal] = None
    actual_fill_price: Optional[Decimal] = None
    remaining_qty: Decimal = Decimal("0")
    intended_qty: Decimal = Decimal("0")
    t1_realized_qty: Optional[Decimal] = None
    regime_at_confirmation: Optional[str] = None

    # State & Lifecycle
    fsm_state: SignalFSMState = "DETECTED"
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    expires_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000) + 300000)
    ttl_seconds: int = 300
    last_updated_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    @computed_field
    @property
    def created_at_str(self) -> str:
        try:
            from zoneinfo import ZoneInfo
            from datetime import datetime
            dt = datetime.fromtimestamp(self.created_at_utc / 1000.0, tz=ZoneInfo("Asia/Kolkata"))
            return dt.strftime("%d %b %Y, %H:%M:%S IST")
        except Exception:
            return ""

    # Realized Execution & Outcomes
    triggered_at_utc: Optional[int] = None
    confirmed_at_utc: Optional[int] = None
    exit_price: Optional[Decimal] = None
    realized_rr: Optional[float] = None
    outcome_status: Optional[str] = None  # WIN_T1, WIN_T2, LOSS_SL, TIME_STOP, RUNNER_TIME_STOP, EXPIRED, INVALIDATED
    paper_order: Optional[dict] = None

    state_history: list[FSMTransitionAudit] = Field(default_factory=list)

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        ts = now_ms or int(time.time() * 1000)
        return ts > self.expires_at_utc and self.fsm_state in ("DETECTED", "VALIDATED", "ARMED")

    def ttl_remaining_seconds(self) -> int:
        now_ms = int(time.time() * 1000)
        # In RUNNER mode, display runner countdown
        if self.fsm_state == "TARGET_1_HIT" and self.runner_time_stop_at_utc:
            return max(0, int((self.runner_time_stop_at_utc - now_ms) / 1000))
        # In ACTIVE mode, display time stop countdown if set
        if self.fsm_state == "CONFIRMED" and self.time_stop_at_utc:
            return max(0, int((self.time_stop_at_utc - now_ms) / 1000))
        return max(0, int((self.expires_at_utc - now_ms) / 1000))


class SignalFSMManager:
    """
    Central Thread-Safe in-memory State Machine Manager with append-only audit persistence.
    """

    def __init__(self):
        self._signals: dict[str, SignalInstance] = {}
        self._audit_log: list[FSMTransitionAudit] = []
        self._lock = threading.RLock()

    def register(self, signal: SignalInstance) -> SignalInstance:
        with self._lock:
            # Initialize default risk levels if not already set (§18)
            if signal.initial_stop_loss is None:
                signal.initial_stop_loss = signal.stop_loss
            if signal.current_stop_loss is None:
                signal.current_stop_loss = signal.stop_loss
            if signal.t1_price is None:
                signal.t1_price = signal.target_1
            if signal.t2_price is None:
                signal.t2_price = signal.target_2

            # Compute initial Risk R based on entry trigger, NOT spot at signal creation
            entry_ref = signal.trigger if signal.trigger and signal.trigger > 0 else signal.spot_price
            risk_r = abs(entry_ref - signal.stop_loss)
            signal.risk_r = risk_r

            # Pre-compute breakeven trigger (+0.8R) anchored to ENTRY
            if signal.direction == "LONG_CALL":
                be_price = entry_ref + (risk_r * Decimal("0.8"))
                if be_price <= entry_ref:
                    be_price = entry_ref + (Decimal("1.0") if risk_r == 0 else abs(risk_r * Decimal("0.8")))
            else:
                be_price = entry_ref - (risk_r * Decimal("0.8"))
                if be_price >= entry_ref:
                    be_price = entry_ref - (Decimal("1.0") if risk_r == 0 else abs(risk_r * Decimal("0.8")))

            signal.breakeven_trigger_price = be_price
            signal.breakeven_activation_price = be_price

            # Pre-entry trigger expiry based on signal.ttl_seconds
            if signal.ttl_seconds and signal.ttl_seconds > 0:
                signal.expires_at_utc = signal.created_at_utc + (signal.ttl_seconds * 1000)

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

            # Persist newly registered signal locally and to PostgreSQL
            try:
                import asyncio
                from app.signals.signals_persistence import persist_executed_signal, save_signals_state_local
                save_signals_state_local()
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(persist_executed_signal(signal))
            except (RuntimeError, Exception):
                pass

            return signal

    def get(self, signal_id: str) -> Optional[SignalInstance]:
        with self._lock:
            return self._signals.get(signal_id)

    def delete(self, signal_id: str) -> bool:
        """Remove a signal and its transitions from in-memory state."""
        with self._lock:
            if signal_id in self._signals:
                del self._signals[signal_id]
                self._audit_log = [a for a in self._audit_log if a.signal_id != signal_id]
                try:
                    from app.signals.signals_persistence import save_signals_state_local
                    save_signals_state_local()
                except Exception:
                    pass
                logger.info("fsm_signal_deleted", signal_id=signal_id)
                return True
            return False

    def sweep_expired(self, now_ms: Optional[int] = None) -> dict[str, int]:
        """Expire stale pre-trigger signals and stale runners; prune terminal overflow.

        Returns counts {expired, runner_stopped, pruned} so callers can log/broadcast.
        Safe to call on every read path (active list, scanner, outcome tick).
        """
        with self._lock:
            now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
            expired = 0
            runner_stopped = 0
            # 1. Market-close expiry & Pre-trigger TTL expiry (DETECTED/VALIDATED/ARMED)
            from app.services.calendar_service import calendar_service
            is_market_closed = not calendar_service.can_trade_now().allowed

            for sig in list(self._signals.values()):
                try:
                    if sig.fsm_state in ("DETECTED", "VALIDATED", "ARMED") or (sig.fsm_state == "CONFIRMED" and not sig.actual_fill_price and not sig.paper_order):
                        if is_market_closed:
                            ok, _ = self.transition(sig.signal_id, "EXPIRED", reason="MARKET_CLOSED")
                            if ok:
                                expired += 1
                            continue
                        elif sig.is_expired(now_ms):
                            ok, _ = self.transition(sig.signal_id, "EXPIRED", reason="TTL_EXCEEDED")
                            if ok:
                                expired += 1
                            continue
                    # 2. Runner TTL expiry — TARGET_1_HIT runners must not block dedup forever
                    elif sig.fsm_state == "TARGET_1_HIT" and sig.runner_time_stop_at_utc and now_ms > sig.runner_time_stop_at_utc:
                        ok, _ = self.transition(sig.signal_id, "RUNNER_TIME_STOP_HIT", reason="RUNNER_TTL_EXCEEDED")
                        if ok:
                            runner_stopped += 1
                    # 3. Active trade time-stop auto-fire (prevents zombie active trades)
                    elif sig.fsm_state == "CONFIRMED" and sig.time_stop_at_utc and now_ms > sig.time_stop_at_utc:
                        ok, _ = self.transition(sig.signal_id, "TIME_STOP_HIT", reason="TIME_STOP_EXCEEDED")
                        if ok:
                            runner_stopped += 1
                except Exception:
                    continue
            # 4. Bound memory: prune oldest terminal signals beyond cap
            pruned = 0
            try:
                if len(self._signals) > 200:
                    terminal = [s for s in self._signals.values() if s.fsm_state in ("CLOSED", "EXPIRED", "INVALIDATED", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT")]
                    terminal.sort(key=lambda s: s.last_updated_utc)
                    overflow = len(self._signals) - 200
                    for s in terminal[:overflow]:
                        self._signals.pop(s.signal_id, None)
                        pruned += 1
                # Also bound in-memory audit log
                if len(self._audit_log) > 1000:
                    self._audit_log = self._audit_log[-1000:]
            except Exception:
                pass
            if expired or runner_stopped or pruned:
                logger.info("fsm_sweep", expired=expired, runner_stopped=runner_stopped, pruned=pruned)
            return {"expired": expired, "runner_stopped": runner_stopped, "pruned": pruned}

    def list_active(self, underlying: Optional[str] = None, strategy: Optional[str] = None) -> list[SignalInstance]:
        with self._lock:
            self.sweep_expired()
            res = []
            for s in self._signals.values():
                if underlying and s.underlying != underlying.upper():
                    continue
                if strategy and s.strategy != strategy.upper():
                    continue
                res.append(s)
            # Sort so ACTIVE & CONFIRMED appear at top, newest first
            state_order = {
                "CONFIRMED": 0,
                "TARGET_1_HIT": 1,
                "TRIGGERED": 2,
                "ARMED": 3,
                "VALIDATED": 4,
                "DETECTED": 5,
                "TARGET_2_HIT": 6,
                "STOP_LOSS_HIT": 7,
                "TIME_STOP_HIT": 8,
                "RUNNER_TIME_STOP_HIT": 9,
                "EXPIRED": 10,
                "INVALIDATED": 11,
                "CLOSED": 12,
            }
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
        with self._lock:
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

            # Update specific timestamps & Two-Clock Lifecycle transitions (§6, §20)
            if to_state == "TRIGGERED":
                sig.triggered_at_utc = sig.last_updated_utc
            elif to_state == "CONFIRMED":
                sig.confirmed_at_utc = sig.last_updated_utc
                # Anchor Active Trade Holding Time-Stop (§18, §20)
                if sig.time_stop_at_utc is None:
                    duration_sec = sig.time_stop_seconds or (900 if sig.is_scalp else 4500)
                    sig.time_stop_at_utc = sig.last_updated_utc + (duration_sec * 1000)
            elif to_state == "TARGET_1_HIT":
                sig.t1_hit = True
                sig.t1_fill_timestamp = sig.last_updated_utc
                sig.exit_price = market_price
                sig.outcome_status = "WIN_T1"
                sig.realized_rr = sig.risk_reward_t1

                # Disable original TTL clock permanently and activate Runner Clock (§6.2, §20)
                runner_ttl_sec = sig.runner_ttl_seconds or 300
                sig.runner_time_stop_at_utc = sig.last_updated_utc + (runner_ttl_sec * 1000)

                # Auto-ratchet stop loss to entry (Cost) on T1 hit (§19)
                if not sig.breakeven_activated:
                    sig.breakeven_activated = True
                    cost_ref = sig.actual_fill_price or sig.entry_min or sig.trigger
                    if sig.direction == "LONG_CALL":
                        sig.current_stop_loss = max(sig.current_stop_loss or sig.stop_loss, cost_ref)
                    else:
                        sig.current_stop_loss = min(sig.current_stop_loss or sig.stop_loss, cost_ref)

            elif to_state == "TARGET_2_HIT":
                sig.t2_hit = True
                sig.exit_price = market_price
                sig.outcome_status = "WIN_T2"
                sig.realized_rr = sig.risk_reward_t2
            elif to_state == "STOP_LOSS_HIT":
                sig.exit_price = market_price
                sig.outcome_status = "LOSS_SL"
                sig.realized_rr = -1.0 if not sig.breakeven_activated else 0.0
            elif to_state == "TIME_STOP_HIT":
                sig.exit_price = market_price
                sig.outcome_status = "TIME_STOP"
                sig.realized_rr = 0.0
            elif to_state == "RUNNER_TIME_STOP_HIT":
                sig.exit_price = market_price
                sig.outcome_status = "RUNNER_TIME_STOP"
                sig.realized_rr = sig.risk_reward_t1
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

            # Sync transition to audit ledger & Supabase
            try:
                from app.signals.audit_ledger import signal_audit_ledger
                signal_audit_ledger.record_state_transition(
                    signal_id=signal_id,
                    to_state=to_state,
                    market_price=float(market_price) if market_price is not None else None,
                    reason=reason,
                )
            except Exception as te:
                logger.debug("fsm_audit_sync_failed", signal_id=signal_id, error=str(te))

            # Persist updated SignalInstance locally and to PostgreSQL
            try:
                import asyncio
                from app.signals.signals_persistence import persist_executed_signal, save_signals_state_local
                save_signals_state_local()
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.create_task(persist_executed_signal(sig))
            except (RuntimeError, Exception):
                pass

            return True, None

    def ratchet_breakeven(self, signal_id: str, market_price: Decimal) -> bool:
        """Activate +0.8R Breakeven Ratchet (§19). Moves stop loss to cost/entry."""
        sig = self._signals.get(signal_id)
        if not sig or sig.breakeven_activated:
            return False
        if sig.fsm_state not in ("CONFIRMED", "TARGET_1_HIT"):
            return False

        cost_ref = sig.actual_fill_price or sig.entry_price or sig.trigger or sig.entry_min or sig.spot_price
        if sig.direction == "LONG_CALL":
            new_sl = cost_ref
            # Ensure stop loss does not move beyond current market price
            if market_price is not None and new_sl >= market_price:
                new_sl = market_price - Decimal("0.05")
            if sig.current_stop_loss is not None and new_sl <= sig.current_stop_loss:
                return False  # stop cannot move backward
            sig.current_stop_loss = new_sl
        else:
            new_sl = cost_ref
            # Ensure stop loss does not move beyond current market price
            if market_price is not None and new_sl <= market_price:
                new_sl = market_price + Decimal("0.05")
            if sig.current_stop_loss is not None and new_sl >= sig.current_stop_loss:
                return False  # stop cannot move backward
            sig.current_stop_loss = new_sl

        sig.breakeven_activated = True
        audit = FSMTransitionAudit(
            signal_id=signal_id,
            from_state=sig.fsm_state,
            to_state=sig.fsm_state,
            market_price=market_price,
            reason_code="BREAKEVEN_RATCHET_ACTIVATED",
            guard_snapshot={"new_sl": float(new_sl), "trigger_price": float(market_price)},
        )
        sig.state_history.append(audit)
        self._audit_log.append(audit)
        logger.info("fsm_breakeven_ratchet", signal_id=signal_id, new_sl=float(new_sl))

        try:
            from app.signals.signals_persistence import save_signals_state_local
            save_signals_state_local()
        except Exception:
            pass

        return True

    def evaluate_tick(
        self,
        sig: SignalInstance,
        tick_price: Decimal,
        tick_timestamp_ms: Optional[int] = None,
    ) -> Optional[str]:
        """Convenience method delegating to deterministic evaluate_tick."""
        action, reason = evaluate_tick(sig, tick_price, tick_timestamp_ms)
        if reason == "BE_ACTIVATED":
            return "BE_ACTIVATED"
        return action



def evaluate_tick(
    sig: SignalInstance,
    tick_price: Decimal,
    tick_timestamp_ms: Optional[int] = None,
) -> tuple[Optional[SignalFSMState], str]:
    """
    Deterministic Tick Evaluation (§21)
    Ordered Priority:
      1. STOP_HIT (highest priority)
      2. T2_HIT (in RUNNER) / T1_HIT (in ACTIVE)
      3. Time-Stop (RUNNER_TIME_STOP_HIT in RUNNER / TIME_STOP_HIT in ACTIVE)
      4. BE_ACTIVATED (returns None state but signals BE ratchet)
    """
    ts = tick_timestamp_ms or int(time.time() * 1000)
    direction = sig.direction
    curr_sl = sig.current_stop_loss or sig.stop_loss

    # Reject non-positive or corrupted prices immediately
    if tick_price <= Decimal("0"):
        return None, "INVALID_PRICE"

    # 1. Stop Loss Check (Highest Priority)
    if direction == "LONG_CALL" and tick_price <= curr_sl:
        return "STOP_LOSS_HIT", "STOP_LOSS_BREACHED"
    elif direction == "LONG_PUT" and tick_price >= curr_sl:
        return "STOP_LOSS_HIT", "STOP_LOSS_BREACHED"

    # 2. RUNNER State Evaluation (Position already achieved T1)
    if sig.fsm_state == "TARGET_1_HIT":
        t2 = sig.t2_price or sig.target_2
        # Check T2 Hit
        if direction == "LONG_CALL" and tick_price >= t2:
            return "TARGET_2_HIT", "TARGET_2_ACHIEVED"
        elif direction == "LONG_PUT" and tick_price <= t2:
            return "TARGET_2_HIT", "TARGET_2_ACHIEVED"

        # Check Runner Time-Stop (Original TTL is structurally unreachable)
        if sig.runner_time_stop_at_utc and ts > sig.runner_time_stop_at_utc:
            return "RUNNER_TIME_STOP_HIT", "RUNNER_TIME_STOP_EXCEEDED"

        # Breakeven trigger in runner
        be_trig = sig.breakeven_trigger_price or sig.breakeven_activation_price
        if not sig.breakeven_activated and be_trig:
            if (direction == "LONG_CALL" and tick_price >= be_trig) or \
               (direction == "LONG_PUT" and tick_price <= be_trig):
                return None, "BE_ACTIVATED"

        return None, "HOLD_RUNNER"

    # 3. ACTIVE / CONFIRMED State Evaluation
    if sig.fsm_state == "CONFIRMED":
        t1 = sig.t1_price or sig.target_1
        # Check T1 Hit
        if direction == "LONG_CALL" and tick_price >= t1:
            return "TARGET_1_HIT", "TARGET_1_ACHIEVED"
        elif direction == "LONG_PUT" and tick_price <= t1:
            return "TARGET_1_HIT", "TARGET_1_ACHIEVED"

        # Check Active Time-Stop
        if sig.time_stop_at_utc and ts > sig.time_stop_at_utc:
            return "TIME_STOP_HIT", "TIME_STOP_EXCEEDED"

        # Check +0.8R Breakeven Trigger
        be_trig = sig.breakeven_trigger_price or sig.breakeven_activation_price
        if not sig.breakeven_activated and be_trig:
            if (direction == "LONG_CALL" and tick_price >= be_trig) or \
               (direction == "LONG_PUT" and tick_price <= be_trig):
                return None, "BE_ACTIVATED"

        return None, "HOLD_ACTIVE"

    return None, "NO_ACTION"


signal_fsm = SignalFSMManager()
