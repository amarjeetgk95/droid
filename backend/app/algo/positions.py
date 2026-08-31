"""
Position Manager & Exit Engine — §62-66

Tracks actual exposure, handles SL/TP/trailing/time/technical/regime/daily/circuit/emergency
Emergency exit failures → ORPHANED_ALERT (§64-65), never assume closed.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Literal, Any
import structlog

from app.algo.money import D

logger = structlog.get_logger()

ExitTrigger = Literal["STOP_LOSS","TAKE_PROFIT","TRAILING_STOP","TIME_EXIT","TECHNICAL_REVERSAL","TREND_REVERSAL","AI_REGIME_REVERSAL","DAILY_RISK_LIMIT","END_OF_SESSION","BROKER_FAILURE","CIRCUIT_RECOVERY","EMERGENCY"]
ExitState = Literal["NONE","EXIT_TRIGGERED","EXIT_SUBMITTED","EXIT_PARTIALLY_FILLED","EXIT_FILLED","EXIT_REJECTED","EXIT_BLOCKED_BY_CIRCUIT","EXIT_NETWORK_UNKNOWN","EXIT_RETRYING","ORPHANED_ALERT","CLOSED"]


@dataclass
class Position:
    account_id: Any
    position_id: str
    symbol: str
    underlying: str | None
    instrument_id: str | None
    side: Literal["LONG", "SHORT"]
    quantity: int
    lot_size: int = 1
    average_entry: Decimal = D(0)
    current_price: Decimal = D(0)
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    trailing_stop: Decimal | None = None
    entry_timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_id: str | None = None
    signal_id: Any | None = None
    capital_allocated: Decimal = D(0)
    unrealized_pnl: Decimal = D(0)
    realized_pnl: Decimal = D(0)
    exit_state: ExitState = "NONE"
    is_open: bool = True
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    greeks: dict = field(default_factory=dict)

    def refresh_pnl(self) -> None:
        if not self.is_open:
            return
        mult = D(1) if self.side == "LONG" else D(-1)
        self.unrealized_pnl = (D(self.current_price) - D(self.average_entry)) * D(self.quantity) * mult
        self.updated_at = datetime.now(timezone.utc)

    def is_stop_hit(self) -> bool:
        if not self.stop_price or not self.is_open:
            return False
        if self.side == "LONG":
            return D(self.current_price) <= D(self.stop_price)
        return D(self.current_price) >= D(self.stop_price)

    def is_target_hit(self) -> bool:
        if not self.target_price or not self.is_open:
            return False
        if self.side == "LONG":
            return D(self.current_price) >= D(self.target_price)
        return D(self.current_price) <= D(self.target_price)


class PositionManager:
    """Tracks actual exposure; syncs with broker state."""

    def __init__(self):
        self._positions: dict[str, Position] = {}  # position_id -> Position (keyed by account+position_id for isolation)

    def _key(self, account_id: Any, position_id: str) -> str:
        return f"{account_id}:{position_id}"

    def upsert(self, pos: Position) -> Position:
        key = self._key(pos.account_id, pos.position_id)
        existing = self._positions.get(key)
        if existing:
            # Merge — preserve exit_state if orphaned
            pos.exit_state = existing.exit_state if existing.exit_state == "ORPHANED_ALERT" else pos.exit_state
        self._positions[key] = pos
        pos.refresh_pnl()
        logger.info("position_upsert", position_id=pos.position_id, qty=pos.quantity, side=pos.side)
        return pos

    def get(self, account_id: Any, position_id: str) -> Position | None:
        return self._positions.get(self._key(account_id, position_id))

    def list_open(self, account_id: Any) -> list[Position]:
        return [p for k, p in self._positions.items() if k.startswith(f"{account_id}:") and p.is_open]

    def list_all(self, account_id: Any) -> list[Position]:
        return [p for k, p in self._positions.items() if k.startswith(f"{account_id}:")]

    def mark_closed(self, account_id: Any, position_id: str, exit_price: Decimal | None = None) -> Position | None:
        pos = self.get(account_id, position_id)
        if not pos:
            return None
        if exit_price is not None:
            mult = D(1) if pos.side == "LONG" else D(-1)
            pos.realized_pnl = pos.realized_pnl + (D(exit_price) - D(pos.average_entry)) * D(pos.quantity) * mult
        pos.is_open = False
        pos.exit_state = "CLOSED"
        pos.updated_at = datetime.now(timezone.utc)
        return pos

    def update_price(self, account_id: Any, position_id: str, current_price: Decimal) -> None:
        pos = self.get(account_id, position_id)
        if pos:
            pos.current_price = D(current_price)
            pos.refresh_pnl()
            # trailing stop update
            if pos.trailing_stop is not None and pos.is_open:
                if pos.side == "LONG":
                    # trail up
                    new_stop = D(current_price) - D(pos.trailing_stop)
                    if pos.stop_price is None or new_stop > D(pos.stop_price):
                        pos.stop_price = new_stop
                else:
                    new_stop = D(current_price) + D(pos.trailing_stop)
                    if pos.stop_price is None or new_stop < D(pos.stop_price):
                        pos.stop_price = new_stop

    def sync_from_broker(self, account_id: Any, broker_positions: list[dict]) -> None:
        """Reconcile internal vs broker (§71) — broker is source of truth for quantity."""
        broker_ids = set()
        for bp in broker_positions:
            pid = bp.get("position_id") or bp.get("symbol")
            broker_ids.add(pid)
            existing = self.get(account_id, pid)
            if existing:
                # Update to broker reality
                existing.quantity = int(bp.get("quantity", existing.quantity))
                existing.average_entry = D(bp.get("average_price", existing.average_entry))
                if existing.quantity == 0:
                    existing.is_open = False
                    existing.exit_state = "CLOSED"
            else:
                self.upsert(Position(
                    account_id=account_id, position_id=pid,
                    symbol=bp.get("symbol", pid), underlying=bp.get("underlying"),
                    instrument_id=bp.get("instrument_id"), side=bp.get("side", "LONG"),
                    quantity=int(bp.get("quantity", 0)), average_entry=D(bp.get("average_price", 0)),
                    current_price=D(bp.get("ltp", 0)), greeks=bp.get("greeks", {}),
                ))
        # Any internal open not in broker → potential orphan; mark for reconciliation
        for pos in self.list_open(account_id):
            if pos.position_id not in broker_ids and broker_positions is not None:
                logger.warning("position_orphan_detected", position_id=pos.position_id)


position_manager = PositionManager()


# ── Exit Engine — §63-66 ───────────────────────────────────────────────

class ExitEngine:
    """
    Supports SL/TP/trailing/time/technical/regime/daily/circuit/emergency.
    AI must never delay a hard protective exit (§63).
    """

    def evaluate(self, pos: Position, context: dict) -> tuple[bool, ExitTrigger | None, str | None]:
        """
        Returns (should_exit, trigger_type, reason)
        Checks in priority order: emergency > stop > target > trailing > time > technical > regime > daily
        """
        if not pos.is_open:
            return False, None, "POSITION_ALREADY_CLOSED"
        # Emergency / orphaned already handled elsewhere
        if pos.exit_state == "ORPHANED_ALERT":
            return True, "EMERGENCY", "ORPHANED_RETRY"

        # End-of-session
        if context.get("is_end_of_session"):
            return True, "END_OF_SESSION", "END_OF_SESSION_EXIT"

        # Daily risk limit
        if context.get("daily_loss_hit"):
            return True, "DAILY_RISK_LIMIT", "DAILY_LOSS_LIMIT_HIT"

        # Circuit recovery — if previously blocked, attempt again when circuit clears
        if pos.exit_state == "EXIT_BLOCKED_BY_CIRCUIT" and not context.get("has_circuit"):
            return True, "CIRCUIT_RECOVERY", "CIRCUIT_CLEARED_RETRY"

        # Hard stops — must never be delayed by AI
        if pos.is_stop_hit():
            return True, "STOP_LOSS", f"STOP_HIT_{pos.stop_price}"
        if pos.is_target_hit():
            return True, "TAKE_PROFIT", f"TARGET_HIT_{pos.target_price}"

        # Time exit
        max_hold = context.get("max_hold_seconds")
        if max_hold and (datetime.now(timezone.utc) - pos.entry_timestamp).total_seconds() >= max_hold:
            return True, "TIME_EXIT", "MAX_HOLD_EXCEEDED"

        # Technical / trend reversal
        if context.get("technical_reversal"):
            return True, "TECHNICAL_REVERSAL", "TECHNICAL_REVERSAL_SIGNAL"
        if context.get("trend_reversal"):
            return True, "TREND_REVERSAL", "TREND_REVERSAL_SIGNAL"
        if context.get("ai_regime_reversal"):
            return True, "AI_REGIME_REVERSAL", "AI_REGIME_REVERSAL"

        # Broker failure → emergency
        if context.get("broker_failure"):
            return True, "BROKER_FAILURE", "BROKER_FAILURE_EMERGENCY"

        return False, None, None

    async def trigger_exit(
        self,
        pos: Position,
        trigger: ExitTrigger,
        order_manager=None,
        is_emergency: bool = False,
    ) -> dict:
        """
        Submit exit order. Handle failures per §64.
        Returns result dict with status.
        """
        if is_emergency:
            order_type = "MARKET"  # emergency prioritizes risk reduction §56 §63
        else:
            order_type = "MARKETABLE_LIMIT"

        pos.exit_state = "EXIT_TRIGGERED"
        pos.updated_at = datetime.now(timezone.utc)
        logger.info("exit_triggered", position_id=pos.position_id, trigger=trigger, emergency=is_emergency)

        # Create exit order intent via OrderManager
        if order_manager is None:
            from app.algo.execution import order_manager as om
            order_manager = om

        side = "SELL" if pos.side == "LONG" else "BUY"
        try:
            rec = order_manager.create_intent(
                account_id=pos.account_id, symbol=pos.symbol, side=side,
                quantity=pos.quantity, price=pos.current_price, order_type=order_type,
                instrument_id=pos.instrument_id, expected_price=pos.current_price,
                is_paper=True,
            )
            pos.exit_state = "EXIT_SUBMITTED"
            # Submit
            result = await order_manager.submit(rec)
            if result.status == "FILLED":
                pos.exit_state = "EXIT_FILLED"
                # close position only on confirmed fill (§64 do not assume closed)
            elif result.status == "PARTIALLY_FILLED":
                pos.exit_state = "EXIT_PARTIALLY_FILLED"
            elif result.status in ("REJECTED", "TIMED_OUT", "UNKNOWN"):
                pos.exit_state = "EXIT_REJECTED" if result.status == "REJECTED" else ("EXIT_NETWORK_UNKNOWN" if result.status == "UNKNOWN" else "EXIT_RETRYING")
            elif result.status == "RECONCILING":
                pos.exit_state = "EXIT_RETRYING"
            return {"status": result.status, "broker_order_id": result.broker_order_id, "trigger": trigger}
        except Exception as e:
            logger.error("exit_submit_failed", error=str(e), position_id=pos.position_id)
            # Do not assume closed, do not clear position, reconcile & retry (§64)
            if "circuit" in str(e).lower():
                pos.exit_state = "EXIT_BLOCKED_BY_CIRCUIT"
            else:
                pos.exit_state = "EXIT_NETWORK_UNKNOWN"
            return {"status": pos.exit_state, "error": str(e), "trigger": trigger}

    def handle_exit_failure(self, pos: Position, result_status: str) -> None:
        """§64-65 state machine after exit attempt."""
        if result_status in ("REJECTED","TIMED_OUT","EXIT_NETWORK_UNKNOWN","EXIT_BLOCKED_BY_CIRCUIT","PARTIALLY_FILLED"):
            # Do not assume closed. Reconcile, retry via controlled logic, escalate.
            if pos.exit_state in ("EXIT_REJECTED","EXIT_NETWORK_UNKNOWN","EXIT_BLOCKED_BY_CIRCUIT"):
                # If already retried and still exposed → ORPHANED_ALERT
                # Simplified: if second failure, escalate
                pos.exit_state = "ORPHANED_ALERT"
                logger.critical("position_orphaned_alert", position_id=pos.position_id, status=result_status)
            else:
                pos.exit_state = "EXIT_RETRYING"  # type: ignore
        # ORPHANED_ALERT blocks new entries, continues monitoring (§65)


exit_engine = ExitEngine()
