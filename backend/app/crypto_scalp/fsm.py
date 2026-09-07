"""
Institutional Crypto 11-State Deterministic Finite State Machine (FSM) & Immutable Transition Audit Log
States:
  DETECTED -> VALIDATED -> ARMED -> TRIGGERED -> CONFIRMED -> TARGET_1_HIT -> TARGET_2_HIT / STOP_LOSS_HIT -> CLOSED
Terminal states: TARGET_2_HIT, STOP_LOSS_HIT, TIME_STOP_HIT, RUNNER_TIME_STOP_HIT, INVALIDATED, EXPIRED, CLOSED
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

CryptoFSMState = Literal[
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

ALLOWED_CRYPTO_TRANSITIONS: dict[CryptoFSMState, set[CryptoFSMState]] = {
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


class CryptoFSMTransitionAudit(BaseModel):
    transition_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    from_state: CryptoFSMState
    to_state: CryptoFSMState
    market_price: Optional[Decimal] = None
    reason_code: str = "STATE_UPDATE"
    processed_timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    guard_snapshot: dict = Field(default_factory=dict)


class CryptoSignalInstance(BaseModel):
    signal_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    symbol: str = "BTCUSDT"
    asset: str = "BTC"
    direction: Literal["LONG", "SHORT"] = "LONG"
    strategy: str
    strategy_name: str = ""
    timeframe: str = "1m"
    is_scalp: bool = True
    spot_price: Decimal
    trigger: Decimal
    stop_loss: Decimal
    initial_stop_loss: Optional[Decimal] = None
    current_stop_loss: Optional[Decimal] = None
    target_1: Decimal
    target_2: Decimal
    t1_price: Optional[Decimal] = None
    t2_price: Optional[Decimal] = None
    risk_points: Decimal
    risk_r: Optional[Decimal] = None
    risk_reward_t1: float = 1.5
    risk_reward_t2: float = 2.5
    confidence: float = 75.0
    confluence_breakdown: dict = Field(default_factory=dict)
    rationale: list[str] = Field(default_factory=list)

    # Breakeven Ratchet (+0.8R)
    breakeven_activated: bool = False
    breakeven_trigger_price: Optional[Decimal] = None

    # Two-Clock Lifecycles & Runner Clock
    ttl_seconds: int = 180  # Pre-entry trigger TTL
    time_stop_seconds: Optional[int] = 900  # Active holding time-stop
    runner_ttl_seconds: Optional[int] = 300  # Runner clock after T1
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    expires_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000) + 180000)
    time_stop_at_utc: Optional[int] = None
    runner_time_stop_at_utc: Optional[int] = None
    last_updated_utc: int = Field(default_factory=lambda: int(time.time() * 1000))

    # Position Sizing & Capital Allocation
    quantity: float = 0.0
    intended_qty: Decimal = Decimal("0")
    remaining_qty: Decimal = Decimal("0")
    t1_realized_qty: Optional[Decimal] = None
    notional_usd: float = 0.0
    max_usd_loss: float = 0.0

    # Staged Target Execution
    t1_hit: bool = False
    t1_fill_timestamp: Optional[int] = None
    t2_hit: bool = False

    # Execution & Fills
    entry_price: Optional[Decimal] = None
    actual_fill_price: Optional[Decimal] = None
    exit_price: Optional[Decimal] = None
    realized_rr: Optional[float] = None
    realized_rr_gross: Optional[float] = None
    realized_rr_net: Optional[float] = None
    fees_usd: float = 0.0
    slippage_usd: float = 0.0
    net_pnl_usd: float = 0.0
    terminal_outcome: Optional[str] = None  # FULL_WIN, PARTIAL_WIN, BREAKEVEN, STOP_LOSS_HIT, TIME_STOP_LOSS, EXPIRED

    # FSM State & Audit
    fsm_state: CryptoFSMState = "DETECTED"
    state_history: list[CryptoFSMTransitionAudit] = Field(default_factory=list)

    @computed_field
    @property
    def created_at_str(self) -> str:
        try:
            from datetime import datetime, timezone
            dt = datetime.fromtimestamp(self.created_at_utc / 1000.0, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        except Exception:
            return ""

    def is_expired(self, now_ms: Optional[int] = None) -> bool:
        ts = now_ms or int(time.time() * 1000)
        # TRIGGERED included: a triggered signal that never confirms must still
        # expire at TTL instead of leaking forever with allocated open risk.
        return ts > self.expires_at_utc and self.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED")

    def ttl_remaining_seconds(self) -> int:
        now_ms = int(time.time() * 1000)
        if self.fsm_state == "TARGET_1_HIT" and self.runner_time_stop_at_utc:
            return max(0, int((self.runner_time_stop_at_utc - now_ms) / 1000))
        if self.fsm_state == "CONFIRMED" and self.time_stop_at_utc:
            return max(0, int((self.time_stop_at_utc - now_ms) / 1000))
        return max(0, int((self.expires_at_utc - now_ms) / 1000))


class CryptoSignalFSMManager:
    """
    Central Thread-Safe in-memory State Machine Manager for Crypto.
    Maintains append-only audit trail and orchestrates two-clock lifecycles.
    """

    def __init__(self):
        self._signals: dict[str, CryptoSignalInstance] = {}
        self._audit_log: list[CryptoFSMTransitionAudit] = []
        self._lock = threading.RLock()

    def register(self, signal: CryptoSignalInstance) -> CryptoSignalInstance:
        with self._lock:
            if signal.initial_stop_loss is None:
                signal.initial_stop_loss = signal.stop_loss
            if signal.current_stop_loss is None:
                signal.current_stop_loss = signal.stop_loss
            if signal.t1_price is None:
                signal.t1_price = signal.target_1
            if signal.t2_price is None:
                signal.t2_price = signal.target_2

            # Compute initial Risk R anchored to trigger entry
            entry_ref = signal.trigger if signal.trigger and signal.trigger > Decimal("0") else signal.spot_price
            risk_r = abs(entry_ref - signal.stop_loss)
            signal.risk_r = risk_r

            # Pre-compute breakeven trigger price (+0.8R)
            if signal.direction == "LONG":
                be_price = entry_ref + (risk_r * Decimal("0.8"))
            else:
                be_price = entry_ref - (risk_r * Decimal("0.8"))
            signal.breakeven_trigger_price = be_price

            # Pre-entry trigger expiry based on signal.ttl_seconds
            if signal.ttl_seconds and signal.ttl_seconds > 0:
                signal.expires_at_utc = signal.created_at_utc + (signal.ttl_seconds * 1000)

            # Set remaining quantity
            if signal.quantity > 0 and signal.intended_qty == Decimal("0"):
                signal.intended_qty = Decimal(str(signal.quantity))
                signal.remaining_qty = Decimal(str(signal.quantity))

            self._signals[signal.signal_id] = signal
            audit = CryptoFSMTransitionAudit(
                signal_id=signal.signal_id,
                from_state="DETECTED",
                to_state=signal.fsm_state,
                market_price=signal.spot_price,
                reason_code="SIGNAL_REGISTERED",
            )
            signal.state_history.append(audit)
            self._audit_log.append(audit)

            # Persist locally and to PostgreSQL
            try:
                from app.crypto_scalp.persistence import save_crypto_signals_state_local
                save_crypto_signals_state_local()
            except Exception:
                pass

            return signal

    def get(self, signal_id: str) -> Optional[CryptoSignalInstance]:
        with self._lock:
            return self._signals.get(signal_id)

    def delete(self, signal_id: str) -> bool:
        with self._lock:
            if signal_id in self._signals:
                del self._signals[signal_id]
                # NOTE: audit log is append-only — deleting a signal must never
                # purge its transition history (immutable ledger invariant).
                try:
                    from app.crypto_scalp.persistence import save_crypto_signals_state_local
                    save_crypto_signals_state_local()
                except Exception:
                    pass
                logger.info("crypto_fsm_signal_deleted", signal_id=signal_id)
                return True
            return False

    def sweep_expired(self, now_ms: Optional[int] = None) -> dict[str, int]:
        """Sweep stale pre-trigger signals, expired runners, and time-stops."""
        with self._lock:
            now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
            expired = 0
            runner_stopped = 0
            time_stopped = 0

            for sig in list(self._signals.values()):
                try:
                    # 1. Pre-trigger expiry (DETECTED/VALIDATED/ARMED/TRIGGERED)
                    if sig.fsm_state in ("DETECTED", "VALIDATED", "ARMED", "TRIGGERED"):
                        if sig.is_expired(now_ms):
                            ok, _ = self.transition(sig.signal_id, "EXPIRED", reason="TTL_EXCEEDED")
                            if ok:
                                expired += 1
                            continue

                    # 2. Runner TTL expiry for TARGET_1_HIT
                    elif sig.fsm_state == "TARGET_1_HIT":
                        is_runner_expired = (sig.runner_time_stop_at_utc and now_ms > sig.runner_time_stop_at_utc) or (
                            sig.t1_fill_timestamp and (now_ms - sig.t1_fill_timestamp > 1800000)
                        )
                        if is_runner_expired:
                            ok, _ = self.transition(sig.signal_id, "RUNNER_TIME_STOP_HIT", reason="RUNNER_TTL_EXCEEDED")
                            if ok:
                                runner_stopped += 1

                    # 3. Active trade time-stop (prevents stagnant active trades)
                    elif sig.fsm_state == "CONFIRMED" and sig.time_stop_at_utc and now_ms > sig.time_stop_at_utc:
                        ok, _ = self.transition(sig.signal_id, "TIME_STOP_HIT", reason="TIME_STOP_EXCEEDED")
                        if ok:
                            time_stopped += 1
                except Exception:
                    continue

            # Bound in-memory cache to prevent leaks
            pruned = 0
            if len(self._signals) > 300:
                terminal = [
                    s for s in self._signals.values()
                    if s.fsm_state in ("CLOSED", "EXPIRED", "INVALIDATED", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT")
                ]
                terminal.sort(key=lambda s: s.last_updated_utc)
                overflow = len(self._signals) - 300
                for s in terminal[:overflow]:
                    self._signals.pop(s.signal_id, None)
                    pruned += 1

            return {"expired": expired, "runner_stopped": runner_stopped, "time_stopped": time_stopped, "pruned": pruned}

    def list_active(
        self,
        symbol: Optional[str] = None,
        strategy: Optional[str] = None,
        include_terminal: bool = False,
    ) -> list[CryptoSignalInstance]:
        with self._lock:
            self.sweep_expired()
            res = []
            terminal_states = {"CLOSED", "EXPIRED", "INVALIDATED", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT"}
            for s in self._signals.values():
                if not include_terminal and s.fsm_state in terminal_states:
                    continue
                if symbol and s.symbol.upper() != symbol.upper():
                    continue
                if strategy and s.strategy.upper() != strategy.upper():
                    continue
                res.append(s)

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
        to_state: CryptoFSMState,
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

            allowed = ALLOWED_CRYPTO_TRANSITIONS.get(sig.fsm_state, set())
            if to_state not in allowed:
                err = f"Illegal crypto FSM transition {sig.fsm_state} -> {to_state}"
                logger.warning("crypto_fsm_illegal_transition", signal_id=signal_id, error=err)
                return False, err

            from_st = sig.fsm_state
            sig.fsm_state = to_state
            sig.last_updated_utc = int(time.time() * 1000)

            # Specific state transitions & lifecycles
            if to_state == "CONFIRMED":
                if sig.time_stop_at_utc is None:
                    duration_sec = sig.time_stop_seconds or (900 if sig.is_scalp else 3600)
                    sig.time_stop_at_utc = sig.last_updated_utc + (duration_sec * 1000)

            elif to_state == "TARGET_1_HIT":
                sig.t1_hit = True
                sig.t1_fill_timestamp = sig.last_updated_utc
                sig.exit_price = market_price
                sig.terminal_outcome = "PARTIAL_WIN"

                # Start Runner Clock (300s / 900s)
                runner_sec = sig.runner_ttl_seconds or 300
                sig.runner_time_stop_at_utc = sig.last_updated_utc + (runner_sec * 1000)

                # Auto-ratchet stop loss to entry (Cost)
                if not sig.breakeven_activated:
                    sig.breakeven_activated = True
                    cost_ref = sig.actual_fill_price or sig.trigger
                    if sig.direction == "LONG":
                        sig.current_stop_loss = max(sig.current_stop_loss or sig.stop_loss, cost_ref)
                    else:
                        sig.current_stop_loss = min(sig.current_stop_loss or sig.stop_loss, cost_ref)

                # R so far (50% booked at T1). The fill reconciler owns the authoritative
                # blended R once it runs; only set a fallback here if it hasn't.
                if sig.realized_rr is None:
                    gross_r = 0.5 * float(sig.risk_reward_t1)
                    friction_r = 0.08
                    sig.realized_rr = gross_r
                    sig.realized_rr_gross = gross_r
                    sig.realized_rr_net = round(gross_r - friction_r, 4)

            elif to_state == "TARGET_2_HIT":
                sig.t2_hit = True
                sig.exit_price = market_price
                sig.terminal_outcome = "FULL_WIN"
                # Blended: 50% booked at T1 (1.5R) + 50% runner at T2 (2.5R) = 2.0R
                if sig.realized_rr is None:
                    gross_r = 0.5 * float(sig.risk_reward_t1) + 0.5 * float(sig.risk_reward_t2)
                    friction_r = 0.08
                    sig.realized_rr = gross_r
                    sig.realized_rr_gross = gross_r
                    sig.realized_rr_net = round(gross_r - friction_r, 4)

            elif to_state == "STOP_LOSS_HIT":
                sig.exit_price = market_price
                if sig.t1_hit:
                    # Runner stopped at breakeven: blended = 0.5 * T1 profit
                    sig.terminal_outcome = "PARTIAL_WIN"
                    gross_r = 0.5 * float(sig.risk_reward_t1)
                elif sig.breakeven_activated:
                    sig.terminal_outcome = "BREAKEVEN"
                    gross_r = 0.0
                else:
                    sig.terminal_outcome = "STOP_LOSS_HIT"
                    gross_r = -1.0
                if sig.realized_rr is None:
                    friction_r = 0.08
                    sig.realized_rr = gross_r
                    sig.realized_rr_gross = gross_r
                    sig.realized_rr_net = round(gross_r - friction_r, 4)

            elif to_state == "TIME_STOP_HIT":
                sig.exit_price = market_price
                sig.terminal_outcome = "TIME_STOP_LOSS"
                if sig.realized_rr is None:
                    gross_r = 0.5 * float(sig.risk_reward_t1) if sig.t1_hit else 0.0
                    friction_r = 0.08
                    sig.realized_rr = gross_r
                    sig.realized_rr_gross = gross_r
                    sig.realized_rr_net = round(gross_r - friction_r, 4)

            elif to_state == "RUNNER_TIME_STOP_HIT":
                sig.exit_price = market_price
                sig.terminal_outcome = "PARTIAL_WIN"
                # Runner was auto-ratcheted to breakeven: blended = 0.5 * T1 profit
                if sig.realized_rr is None:
                    gross_r = 0.5 * float(sig.risk_reward_t1)
                    friction_r = 0.08
                    sig.realized_rr = gross_r
                    sig.realized_rr_gross = gross_r
                    sig.realized_rr_net = round(gross_r - friction_r, 4)

            elif to_state == "EXPIRED":
                sig.terminal_outcome = "EXPIRED"

            elif to_state == "INVALIDATED":
                sig.terminal_outcome = "INVALIDATED"

            audit = CryptoFSMTransitionAudit(
                signal_id=signal_id,
                from_state=from_st,
                to_state=to_state,
                market_price=market_price,
                reason_code=reason,
                guard_snapshot=guard_snapshot or {},
            )
            sig.state_history.append(audit)
            self._audit_log.append(audit)
            logger.info("crypto_fsm_state_transition", signal_id=signal_id, from_state=from_st, to_state=to_state, reason=reason)

            try:
                from app.crypto_scalp.persistence import save_crypto_signals_state_local
                save_crypto_signals_state_local()
            except Exception:
                pass

            return True, None

    def ratchet_breakeven(self, signal_id: str, market_price: Decimal) -> bool:
        """Activate +0.8R Breakeven Ratchet. Moves stop loss to entry fill price."""
        with self._lock:
            sig = self._signals.get(signal_id)
            if not sig or sig.breakeven_activated:
                return False

            sig.breakeven_activated = True
            cost_ref = sig.actual_fill_price or sig.trigger
            if sig.direction == "LONG":
                sig.current_stop_loss = max(sig.current_stop_loss or sig.stop_loss, cost_ref)
            else:
                sig.current_stop_loss = min(sig.current_stop_loss or sig.stop_loss, cost_ref)

            audit = CryptoFSMTransitionAudit(
                signal_id=signal_id,
                from_state=sig.fsm_state,
                to_state=sig.fsm_state,
                market_price=market_price,
                reason_code="BREAKEVEN_RATCHET_ACTIVATED",
            )
            sig.state_history.append(audit)
            self._audit_log.append(audit)
            logger.info("crypto_breakeven_ratchet_activated", signal_id=signal_id, market_price=float(market_price), new_stop=float(sig.current_stop_loss))
            return True

    def evaluate_tick(self, sig: CryptoSignalInstance, market_price: Decimal, now_ms: int) -> Optional[str]:
        """
        Ordered priority evaluation for active signals:
          1. Time Stop
          2. Runner Time Stop
          3. Stop Loss / Breakeven Stop
          4. Target 2 Hit (Runner exit)
          5. Target 1 Hit (Staged partial exit)
          6. Breakeven Ratchet (+0.8R)
        """
        # Active trade time-stop check
        if sig.fsm_state == "CONFIRMED" and sig.time_stop_at_utc and now_ms > sig.time_stop_at_utc:
            return "TIME_STOP_HIT"

        # Runner time-stop check
        if sig.fsm_state == "TARGET_1_HIT" and sig.runner_time_stop_at_utc and now_ms > sig.runner_time_stop_at_utc:
            return "RUNNER_TIME_STOP_HIT"

        is_long = sig.direction == "LONG"
        sl = sig.current_stop_loss or sig.stop_loss
        t1 = sig.t1_price or sig.target_1
        t2 = sig.t2_price or sig.target_2

        # Stop loss breach check
        if is_long and market_price <= sl:
            return "STOP_LOSS_HIT"
        elif not is_long and market_price >= sl:
            return "STOP_LOSS_HIT"

        # Runner target 2 hit (only if in TARGET_1_HIT state)
        if sig.fsm_state == "TARGET_1_HIT":
            if is_long and market_price >= t2:
                return "TARGET_2_HIT"
            elif not is_long and market_price <= t2:
                return "TARGET_2_HIT"

        # Target 1 hit (when in CONFIRMED state)
        if sig.fsm_state == "CONFIRMED":
            if is_long and market_price >= t1:
                return "TARGET_1_HIT"
            elif not is_long and market_price <= t1:
                return "TARGET_1_HIT"

            # +0.8R Breakeven ratchet check before T1
            if not sig.breakeven_activated and sig.breakeven_trigger_price:
                be_trig = sig.breakeven_trigger_price
                if (is_long and market_price >= be_trig) or (not is_long and market_price <= be_trig):
                    return "BE_ACTIVATED"

        return None


crypto_signal_fsm = CryptoSignalFSMManager()
