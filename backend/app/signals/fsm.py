"""
11-State Deterministic Signal Finite State Machine & Immutable Transition Audit Log
States:
  DETECTED -> VALIDATED -> ARMED -> TRIGGERED -> CONFIRMED -> TARGET_1_HIT -> TARGET_2_HIT / STOP_LOSS_HIT -> CLOSED
Terminal states: TARGET_2_HIT, STOP_LOSS_HIT, INVALIDATED, EXPIRED, CLOSED
"""
from __future__ import annotations

import threading
import time
import uuid
from decimal import Decimal
from typing import Literal

import structlog
from pydantic import BaseModel, Field, computed_field

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
    market_price: Decimal | None = None
    reason_code: str = "STATE_UPDATE"
    processed_timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    guard_snapshot: dict = Field(default_factory=dict)


from app.signals.transaction_costs import (
    DEFAULT_COST_SCHEDULE,
    DEFAULT_SIGNAL_TTL_MS,
    FSM_MAX_AUDIT_LOG_ENTRIES,
    FSM_MAX_SIGNALS_IN_MEMORY,
    IndianFNOCostSchedule,
    compute_option_friction_r,
    compute_terminal_outcome,
    estimate_exit_premium,
)

_exit_premium_for_friction = estimate_exit_premium

from app.signals.event_bus import SignalEvent, SignalEventType, signal_event_bus
try:
    from app.signals.handlers import register_default_handlers
    register_default_handlers()
except Exception:
    pass


def _should_use_event_bus() -> bool:
    try:
        from app.core.config import settings
        return getattr(settings, "use_event_bus", True)
    except Exception:
        return True



def _spot_be_reference(sig: SignalInstance) -> Decimal | None:
    """
    Spot-domain breakeven reference for stop-loss ratchets.

    current_stop_loss is evaluated against underlying spot ticks, so the
    ratchet target MUST be a spot price (entry/trigger zone) — never an
    option premium fill. actual_fill_price/entry_price live in the execution
    premium domain for option signals (e.g. ₹118 premium vs ₹23807 spot);
    assigning one as a spot stop fires an instant phantom STOP_LOSS_HIT on
    the next tick. True spot fills (same scale as the trigger) are still
    preferred as the most accurate cost.
    """
    try:
        trig = Decimal(str(sig.trigger or "0"))
    except Exception:
        trig = Decimal(0)
    # Prefer true fills only when they share the trigger's scale (spot fills
    # for spot-tracked signals). A premium fill is orders of magnitude below
    # an index trigger — reject it and fall through to the spot entry zone.
    for cand in (sig.actual_fill_price, sig.entry_price):
        if cand is None:
            continue
        try:
            v = Decimal(str(cand))
        except Exception:
            continue
        if v <= 0:
            continue
        if trig > 0 and v > trig * Decimal("0.5") and v < trig * Decimal("1.5"):
            return v
    for cand in (sig.entry_min, sig.entry_max, sig.trigger, sig.spot_price):
        if cand is None:
            continue
        try:
            v = Decimal(str(cand))
        except Exception:
            continue
        if v > 0:
            return v
    return None


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
    explain: dict | None = None
    option_contract: dict | None = None

    # Version 6.0 Desk & Risk Fields
    signal_type: str = "INTRADAY"  # SCALP, INTRADAY, SWING
    is_scalp: bool = False
    initial_stop_loss: Decimal | None = None
    current_stop_loss: Decimal | None = None
    risk_r: Decimal | None = None

    # Breakeven Ratchet (+0.8R)
    breakeven_activated: bool = False
    breakeven_trigger_price: Decimal | None = None
    breakeven_activation_price: Decimal | None = None

    # Two-Clock Lifecycles (§6, §20)
    time_stop_seconds: int | None = None
    time_stop_at_utc: int | None = None
    runner_time_stop_at_utc: int | None = None
    runner_ttl_seconds: int | None = None

    # Position Sizing & Capital Allocation
    lots: int | None = None
    quantity: int | None = None
    max_rupee_loss: float | None = None

    # Options Intelligence & Multi-Horizon Economics (§40)
    greeks: dict | None = None
    expected_move: dict | None = None
    ai_research: dict | None = None
    path_simulation: dict | None = None

    # Staged Target Execution (§18, §25)
    t1_price: Decimal | None = None
    t2_price: Decimal | None = None
    t1_hit: bool = False
    t1_fill_timestamp: int | None = None
    t2_hit: bool = False

    # Fill Reconciliation & Residual Quantity Tracking (§24, §25)
    entry_price: Decimal | None = None
    actual_fill_price: Decimal | None = None
    remaining_qty: Decimal = Decimal(0)
    intended_qty: Decimal = Decimal(0)
    t1_realized_qty: Decimal | None = None
    regime_at_confirmation: str | None = None

    # State & Lifecycle
    fsm_state: SignalFSMState = "DETECTED"
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    expires_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000) + DEFAULT_SIGNAL_TTL_MS)
    ttl_seconds: int = 300
    last_updated_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    @computed_field
    @property
    def created_at_str(self) -> str:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            dt = datetime.fromtimestamp(self.created_at_utc / 1000.0, tz=ZoneInfo("Asia/Kolkata"))
            return dt.strftime("%d %b %Y, %H:%M:%S IST")
        except Exception:
            return ""

    # Realized Execution & Outcomes
    triggered_at_utc: int | None = None
    confirmed_at_utc: int | None = None
    exit_price: Decimal | None = None
    realized_rr: float | None = None
    realized_rr_gross: float | None = None
    realized_rr_net: float | None = None
    cost_breakdown_r: dict | None = None
    terminal_outcome: str | None = None  # FULL_WIN, PARTIAL_WIN, BREAKEVEN, TIME_STOP_LOSS, STOP_LOSS_HIT, EXPIRED, INVALIDATED
    outcome_status: str | None = None  # WIN_T1, WIN_T2, LOSS_SL, TIME_STOP, RUNNER_TIME_STOP, EXPIRED, INVALIDATED
    paper_order: dict | None = None
    state_history: list[FSMTransitionAudit] = Field(default_factory=list)

    # v3.0 Decoupled Domain Links & Auditable Metadata
    version: int = 1
    execution_intent_id: str | None = None
    position_id: str | None = None
    strategy_version: int = 1
    scoring_version: int = 1
    feature_version: int = 1
    prediction_status: str = "PENDING"
    execution_eligibility: bool = True

    def is_expired(self, now_ms: int | None = None) -> bool:
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

    def to_wire_dict(self) -> dict:
        """Standard frontend-facing serialization."""
        return self.model_dump(mode="json")

    def to_audit_dict(self) -> dict:
        """Comprehensive audit serialization with exact decimal strings."""
        d = self.model_dump(mode="json")
        d.update({
            "signal_id": self.signal_id,
            "fsm_state": self.fsm_state,
            "execution_intent_id": self.execution_intent_id,
            "position_id": self.position_id,
            "strategy_version": self.strategy_version,
            "prediction_status": self.prediction_status,
            "execution_eligibility": self.execution_eligibility,
            "created_at_utc": self.created_at_utc,
            "last_updated_utc": self.last_updated_utc,
            "history_count": len(self.state_history),
        })
        return d

    def to_research_dict(self) -> dict:
        """Point-in-time reproducible research record."""
        return {
            "signal_id": self.signal_id,
            "underlying": self.underlying,
            "strategy": self.strategy,
            "direction": self.direction,
            "timeframe": self.timeframe,
            "strategy_version": self.strategy_version,
            "scoring_version": self.scoring_version,
            "feature_version": self.feature_version,
            "spot_price": float(self.spot_price) if self.spot_price else None,
            "trigger": float(self.trigger) if self.trigger else None,
            "stop_loss": float(self.stop_loss) if self.stop_loss else None,
            "target_1": float(self.target_1) if self.target_1 else None,
            "target_2": float(self.target_2) if self.target_2 else None,
            "realized_rr_net": self.realized_rr_net,
            "terminal_outcome": self.terminal_outcome,
            "created_at_utc": self.created_at_utc,
        }

    # ── Phase 2 Domain Model Views ────────────────────────────────────
    @property
    def definition(self):
        """Immutable view of the strategy decision."""
        from app.signals.signal_model import SignalDefinition
        return SignalDefinition(
            signal_id=self.signal_id,
            underlying=self.underlying,
            strategy=self.strategy,
            direction=self.direction,
            timeframe=self.timeframe,
            spot_price=self.spot_price,
            entry_min=self.entry_min,
            entry_max=self.entry_max,
            trigger=self.trigger,
            stop_loss=self.stop_loss,
            target_1=self.target_1,
            target_2=self.target_2,
            risk_points=self.risk_points,
            risk_reward_t1=self.risk_reward_t1,
            risk_reward_t2=self.risk_reward_t2,
            confidence=self.confidence,
            signal_type=self.signal_type,
            is_scalp=self.is_scalp,
            ttl_seconds=self.ttl_seconds,
            strategy_version=self.strategy_version,
            scoring_version=self.scoring_version,
            feature_version=self.feature_version,
            created_at_utc=self.created_at_utc,
        )

    @property
    def risk_sizing(self):
        """View of risk engine capital allocation and limits."""
        from app.signals.signal_model import RiskSizing
        return RiskSizing(
            lots=self.lots,
            quantity=self.quantity,
            max_rupee_loss=self.max_rupee_loss,
            risk_r=self.risk_r,
        )

    @property
    def confluence_typed(self):
        """Typed view of multi-domain confluence scoring."""
        from app.signals.signal_model import ConfluenceBreakdown
        try:
            return ConfluenceBreakdown.model_validate(self.confluence_breakdown or {})
        except Exception:
            return ConfluenceBreakdown()

    @property
    def execution_state(self):
        """View of broker execution and fill reconciliation state."""
        from app.signals.signal_model import ExecutionState
        return ExecutionState(
            fsm_state=self.fsm_state,
            initial_stop_loss=self.initial_stop_loss,
            current_stop_loss=self.current_stop_loss,
            breakeven_activated=self.breakeven_activated,
            breakeven_trigger_price=self.breakeven_trigger_price,
            breakeven_activation_price=self.breakeven_activation_price,
            time_stop_seconds=self.time_stop_seconds,
            time_stop_at_utc=self.time_stop_at_utc,
            runner_time_stop_at_utc=self.runner_time_stop_at_utc,
            runner_ttl_seconds=self.runner_ttl_seconds,
            entry_price=self.entry_price,
            actual_fill_price=self.actual_fill_price,
            remaining_qty=self.remaining_qty,
            intended_qty=self.intended_qty,
            t1_price=self.t1_price,
            t2_price=self.t2_price,
            t1_hit=self.t1_hit,
            t1_fill_timestamp=self.t1_fill_timestamp,
            t2_hit=self.t2_hit,
            paper_order=self.paper_order,
            last_updated_utc=self.last_updated_utc,
        )

    @property
    def outcome_typed(self):
        """Typed view of realized financial outcome."""
        from app.signals.signal_model import SignalOutcome
        return SignalOutcome(
            exit_price=self.exit_price,
            realized_rr=self.realized_rr,
            realized_rr_gross=self.realized_rr_gross,
            realized_rr_net=self.realized_rr_net,
            cost_breakdown_r=self.cost_breakdown_r,
            terminal_outcome=self.terminal_outcome,
            outcome_status=self.outcome_status,
        )




def apply_fsm_transition_pure(
    sig: SignalInstance,
    to_state: SignalFSMState,
    market_price: Decimal | None = None,
    timestamp_ms: int | None = None,
    expected_version: int | None = None,
) -> tuple[bool, str | None]:
    """
    Pure state machine transition logic for SignalInstance.
    Enforces allowed transitions, FNO integrity guard, two-clock lifecycle,
    and optimistic concurrency versioning.
    """
    if expected_version is not None and sig.version != expected_version:
        return False, f"Optimistic concurrency conflict: signal version is {sig.version}, expected {expected_version}"

    if sig.fsm_state == to_state:
        return True, None

    allowed = ALLOWED_TRANSITIONS.get(sig.fsm_state, set())
    if to_state not in allowed:
        return False, f"Illegal transition {sig.fsm_state} -> {to_state}"

    # State-Aware F&O Guard (§1): Never allow degraded F&O signals to ARM or TRIGGER
    if to_state in ("ARMED", "TRIGGERED", "CONFIRMED"):
        if sig.confluence_breakdown and sig.confluence_breakdown.get("fno_degraded"):
            return False, "FNO_DATA_DEGRADED_CANNOT_ARM"

    now_ms = timestamp_ms or int(time.time() * 1000)
    sig.fsm_state = to_state
    sig.last_updated_utc = now_ms
    sig.version += 1

    # Update specific timestamps & Two-Clock Lifecycle transitions (§6, §20)
    if to_state == "TRIGGERED":
        sig.triggered_at_utc = now_ms
    elif to_state == "CONFIRMED":
        sig.confirmed_at_utc = now_ms
        # Anchor Active Trade Holding Time-Stop (§18, §20)
        if sig.time_stop_at_utc is None:
            duration_sec = sig.time_stop_seconds or (900 if sig.is_scalp else 4500)
            sig.time_stop_at_utc = now_ms + (duration_sec * 1000)
    elif to_state in (
        "TARGET_1_HIT",
        "TARGET_2_HIT",
        "STOP_LOSS_HIT",
        "TIME_STOP_HIT",
        "RUNNER_TIME_STOP_HIT",
        "EXPIRED",
        "INVALIDATED",
    ):
        outcome = compute_terminal_outcome(to_state, sig, market_price)
        for k, v in outcome.items():
            setattr(sig, k, v)

        if to_state == "TARGET_1_HIT":
            sig.t1_fill_timestamp = now_ms
            # Disable original TTL clock permanently and activate Runner Clock (§6.2, §20)
            runner_ttl_sec = sig.runner_ttl_seconds or 300
            sig.runner_time_stop_at_utc = now_ms + (runner_ttl_sec * 1000)

            # Auto-ratchet stop loss to entry (Cost) on T1 hit (§19).
            if not sig.breakeven_activated:
                sig.breakeven_activated = True
                cost_ref = _spot_be_reference(sig) or sig.stop_loss
                if sig.direction == "LONG_CALL":
                    sig.current_stop_loss = max(sig.current_stop_loss or sig.stop_loss, cost_ref)
                else:
                    sig.current_stop_loss = min(sig.current_stop_loss or sig.stop_loss, cost_ref)

    return True, None


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
            if _should_use_event_bus():
                signal_event_bus.publish_sync(
                    SignalEvent(
                        event_type=SignalEventType.REGISTERED,
                        signal_id=signal.signal_id,
                        occurred_at_utc=signal.created_at_utc,
                        payload=signal.to_wire_dict(),
                    )
                )
            else:
                try:
                    import asyncio

                    from app.signals.signals_persistence import (
                        persist_executed_signal,
                        save_signals_state_local,
                    )
                    save_signals_state_local()
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(persist_executed_signal(signal))
                except (RuntimeError, Exception):
                    pass

            return signal

    def get(self, signal_id: str) -> SignalInstance | None:
        with self._lock:
            return self._signals.get(signal_id)

    def delete(self, signal_id: str) -> bool:
        """Remove a signal and its transitions from in-memory state."""
        with self._lock:
            if signal_id in self._signals:
                del self._signals[signal_id]
                self._audit_log = [a for a in self._audit_log if a.signal_id != signal_id]
                if _should_use_event_bus():
                    signal_event_bus.publish_sync(
                        SignalEvent(
                            event_type=SignalEventType.DELETED,
                            signal_id=signal_id,
                            payload={},
                        )
                    )
                else:
                    try:
                        from app.signals.signals_persistence import save_signals_state_local
                        save_signals_state_local()
                    except Exception:
                        pass
                logger.info("fsm_signal_deleted", signal_id=signal_id)
                return True
            return False

    def sweep_expired(self, now_ms: int | None = None) -> dict[str, int]:
        """Expire stale pre-trigger signals and stale runners; prune terminal overflow.

        Returns counts {expired, runner_stopped, pruned} so callers can log/broadcast.
        Safe to call on every read path (active list, scanner, outcome tick).
        """
        with self._lock:
            now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
            expired = 0
            runner_stopped = 0
            from datetime import datetime
            from zoneinfo import ZoneInfo

            from app.services.calendar_service import calendar_service
            ist_tz = ZoneInfo("Asia/Kolkata")
            now_ist = datetime.fromtimestamp(now_ms / 1000.0, tz=ist_tz)
            today_ist = now_ist.date()
            is_market_closed = not calendar_service.can_trade_now().allowed

            for sig in list(self._signals.values()):
                try:
                    sig_dt = datetime.fromtimestamp(sig.created_at_utc / 1000.0, tz=ist_tz)
                    is_prior_day = sig_dt.date() < today_ist

                    # 1. Market-close or Prior-day expiry for Pre-trigger (DETECTED/VALIDATED/ARMED/TRIGGERED)
                    if sig.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED") or (sig.fsm_state == "CONFIRMED" and not sig.actual_fill_price and not sig.paper_order):
                        if is_prior_day or is_market_closed:
                            ok, _ = self.transition(sig.signal_id, "EXPIRED", reason="MARKET_CLOSED" if is_market_closed else "PRIOR_DAY_EXPIRED")
                            if ok:
                                expired += 1
                            continue
                        elif sig.is_expired(now_ms):
                            ok, _ = self.transition(sig.signal_id, "EXPIRED", reason="TTL_EXCEEDED")
                            if ok:
                                expired += 1
                            continue

                    # 2. Prior-day open positions (intraday MIS positions must never persist across days)
                    elif is_prior_day and sig.fsm_state in ("CONFIRMED", "TARGET_1_HIT"):
                        ok, _ = self.transition(sig.signal_id, "CLOSED", reason="EOD_SESSION_SQUARE_OFF")
                        if ok:
                            runner_stopped += 1
                        continue

                    # 3. Runner TTL expiry — TARGET_1_HIT runners
                    elif sig.fsm_state == "TARGET_1_HIT":
                        if is_market_closed:
                            ok, _ = self.transition(sig.signal_id, "RUNNER_TIME_STOP_HIT", reason="MARKET_CLOSED_RUNNER_CLOSED")
                            if ok:
                                runner_stopped += 1
                            continue
                        # If runner time stop passed, or default 30m window passed
                        is_runner_expired = (sig.runner_time_stop_at_utc and now_ms > sig.runner_time_stop_at_utc) or (sig.t1_fill_timestamp and (now_ms - sig.t1_fill_timestamp > 1800000))
                        if is_runner_expired:
                            ok, _ = self.transition(sig.signal_id, "RUNNER_TIME_STOP_HIT", reason="RUNNER_TTL_EXCEEDED")
                            if ok:
                                runner_stopped += 1

                    # 4. Active trade time-stop auto-fire (prevents zombie active trades)
                    elif sig.fsm_state == "CONFIRMED" and sig.time_stop_at_utc and now_ms > sig.time_stop_at_utc:
                        ok, _ = self.transition(sig.signal_id, "TIME_STOP_HIT", reason="TIME_STOP_EXCEEDED")
                        if ok:
                            runner_stopped += 1
                except Exception:
                    continue
            # 5. Bound memory: prune oldest terminal signals beyond cap
            pruned = 0
            try:
                if len(self._signals) > FSM_MAX_SIGNALS_IN_MEMORY:
                    terminal = [s for s in self._signals.values() if s.fsm_state in ("CLOSED", "EXPIRED", "INVALIDATED", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT")]
                    terminal.sort(key=lambda s: s.last_updated_utc)
                    overflow = len(self._signals) - FSM_MAX_SIGNALS_IN_MEMORY
                    for s in terminal[:overflow]:
                        self._signals.pop(s.signal_id, None)
                        pruned += 1
                # Also bound in-memory audit log
                if len(self._audit_log) > FSM_MAX_AUDIT_LOG_ENTRIES:
                    self._audit_log = self._audit_log[-FSM_MAX_AUDIT_LOG_ENTRIES:]
            except Exception:
                pass
            if expired or runner_stopped or pruned:
                logger.info("fsm_sweep", expired=expired, runner_stopped=runner_stopped, pruned=pruned)
            return {"expired": expired, "runner_stopped": runner_stopped, "pruned": pruned}

    def list_active(self, underlying: str | None = None, strategy: str | None = None, include_terminal: bool = False) -> list[SignalInstance]:
        with self._lock:
            self.sweep_expired()
            res = []
            terminal_states = {"CLOSED", "EXPIRED", "INVALIDATED", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT"}
            for s in self._signals.values():
                if not include_terminal and s.fsm_state in terminal_states:
                    continue
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
        market_price: Decimal | None = None,
        reason: str = "STATE_UPDATE",
        guard_snapshot: dict | None = None,
        expected_version: int | None = None,
    ) -> tuple[bool, str | None]:
        with self._lock:
            sig = self._signals.get(signal_id)
            if not sig:
                return False, "Signal not found"

            from_st = sig.fsm_state
            if from_st == to_state:
                return True, None

            ok, err = apply_fsm_transition_pure(
                sig=sig,
                to_state=to_state,
                market_price=market_price,
                expected_version=expected_version,
            )
            if not ok:
                if "Illegal" in str(err):
                    logger.warning("fsm_illegal_transition", signal_id=signal_id, error=err)
                elif "FNO_DATA_DEGRADED" in str(err):
                    logger.warning("fsm_fno_degraded_arm_blocked", signal_id=signal_id, to_state=to_state)
                return False, err

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
            logger.info("fsm_state_transition", signal_id=signal_id, from_state=from_st, to_state=to_state, reason=reason, version=sig.version)

            if _should_use_event_bus():
                signal_event_bus.publish_sync(
                    SignalEvent(
                        event_type=SignalEventType.TRANSITIONED,
                        signal_id=signal_id,
                        occurred_at_utc=audit.processed_timestamp,
                        payload={
                            "from_state": from_st,
                            "to_state": to_state,
                            "market_price": float(market_price) if market_price is not None else None,
                            "reason": reason,
                            "guard_snapshot": guard_snapshot or {},
                            "version": sig.version,
                        },
                    )
                )
            else:
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

                    from app.signals.signals_persistence import (
                        persist_executed_signal,
                        save_signals_state_local,
                    )
                    save_signals_state_local()
                    loop = asyncio.get_running_loop()
                    if loop.is_running():
                        loop.create_task(persist_executed_signal(sig))
                except (RuntimeError, Exception):
                    pass

            return True, None

    def ratchet_breakeven(self, signal_id: str, market_price: Decimal) -> bool:
        """Activate +0.8R Breakeven Ratchet (§19). Moves stop loss to cost/entry.

        Spot-domain only: the stop is evaluated against underlying spot ticks,
        so the ratchet target is the spot entry zone (never the option premium
        fill — e.g. ₹118 premium vs ₹23807 spot would stop out instantly).
        """
        sig = self._signals.get(signal_id)
        if not sig or sig.breakeven_activated:
            return False
        if sig.fsm_state not in ("CONFIRMED", "TARGET_1_HIT"):
            return False

        cost_ref = _spot_be_reference(sig)
        if cost_ref is None:
            return False
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

        if _should_use_event_bus():
            signal_event_bus.publish_sync(
                SignalEvent(
                    event_type=SignalEventType.BREAKEVEN_ACTIVATED,
                    signal_id=signal_id,
                    occurred_at_utc=audit.processed_timestamp,
                    payload={"new_sl": float(new_sl), "market_price": float(market_price) if market_price is not None else None},
                )
            )
        else:
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
        tick_timestamp_ms: int | None = None,
    ) -> str | None:
        """Convenience method delegating to deterministic evaluate_tick."""
        action, reason = evaluate_tick(sig, tick_price, tick_timestamp_ms)
        if reason == "BE_ACTIVATED":
            return "BE_ACTIVATED"
        return action



def evaluate_tick(
    sig: SignalInstance,
    tick_price: Decimal,
    tick_timestamp_ms: int | None = None,
) -> tuple[SignalFSMState | None, str]:
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
    if tick_price <= Decimal(0):
        return None, "INVALID_PRICE"

    # 1. Stop Loss Check (Highest Priority)
    if direction == "LONG_CALL" and tick_price <= curr_sl or direction == "LONG_PUT" and tick_price >= curr_sl:
        return "STOP_LOSS_HIT", "STOP_LOSS_BREACHED"

    # 2. RUNNER State Evaluation (Position already achieved T1)
    if sig.fsm_state == "TARGET_1_HIT":
        t2 = sig.t2_price or sig.target_2
        # Check T2 Hit
        if direction == "LONG_CALL" and tick_price >= t2 or direction == "LONG_PUT" and tick_price <= t2:
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
        if direction == "LONG_CALL" and tick_price >= t1 or direction == "LONG_PUT" and tick_price <= t1:
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
