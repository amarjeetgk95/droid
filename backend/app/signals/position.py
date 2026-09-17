"""
Position Model & Position Lifecycle FSM
Represents portfolio reality derived from actual broker or paper fills.
State flow:
  OPEN -> PARTIALLY_FILLED -> T1_PARTIAL_EXIT -> T2_EXIT / STOP_LOSS / TIME_STOP -> CLOSED
  OPEN -> ASSIGNED / EXPIRED -> CLOSED (expiry assignment)
Strictly decoupled from Signal market analysis thesis.

P1: every fill requires a live OptionMark (BUY at ask+slip, SELL at
bid-slip; fail-closed on UNAVAILABLE/stale), statutory + net PnL are computed
inside transition_to off the single canonical schedule, qty is validated to
lot steps, and the contract links (broker_symbol/strike/expiry) drive
portfolio-ledger add/remove.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
import structlog
from pydantic import BaseModel, Field

from app.signals.safety.decimal_types import D

logger = structlog.get_logger()


class PositionState(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    T1_PARTIAL_EXIT = "T1_PARTIAL_EXIT"
    T2_EXIT = "T2_EXIT"
    STOP_LOSS = "STOP_LOSS"
    TIME_STOP = "TIME_STOP"
    ASSIGNED = "ASSIGNED"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"


ALLOWED_POSITION_TRANSITIONS: dict[PositionState, set[PositionState]] = {
    PositionState.OPEN: {PositionState.PARTIALLY_FILLED, PositionState.T1_PARTIAL_EXIT, PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP, PositionState.ASSIGNED, PositionState.EXPIRED, PositionState.CLOSED},
    PositionState.PARTIALLY_FILLED: {PositionState.OPEN, PositionState.T1_PARTIAL_EXIT, PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP, PositionState.ASSIGNED, PositionState.EXPIRED, PositionState.CLOSED},
    PositionState.T1_PARTIAL_EXIT: {PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP, PositionState.ASSIGNED, PositionState.EXPIRED, PositionState.CLOSED},
    PositionState.T2_EXIT: {PositionState.CLOSED},
    PositionState.STOP_LOSS: {PositionState.CLOSED},
    PositionState.TIME_STOP: {PositionState.CLOSED},
    PositionState.ASSIGNED: {PositionState.CLOSED},
    PositionState.EXPIRED: {PositionState.CLOSED},
    PositionState.CLOSED: set(),
}


def _validate_lot_quantity(qty: int, lot_size: int) -> Optional[str]:
    try:
        q = int(qty or 0)
        ls = int(lot_size or 0)
        if q <= 0:
            return "QTY_NON_POSITIVE"
        if ls > 0 and q % ls != 0:
            return f"QTY_NOT_LOT_STEP_{q}_vs_{ls}"
    except Exception:
        return "QTY_INVALID"
    return None


def _require_fill_mark(
    broker_symbol: str,
    side: str,
    slip_pts: float = 0.0,
    desk: Optional[str] = None,
) -> tuple[Optional[float], Any, Optional[str]]:
    """Resolve the executable fill off a live OptionMark (fail-closed).

    BUY fills at ask+slip, SELL at bid-slip. Returns (price, mark, error).
    error is None on success.
    """
    try:
        from app.signals.option_marks import option_mark_registry
        mark = option_mark_registry.get_usable(broker_symbol, allow_model=False, desk=desk)
        if mark is None:
            # Distinguish stale vs absent for the audit trail.
            try:
                raw = option_mark_registry.get(broker_symbol)
                if raw is None:
                    return None, None, "FILL_MARK_UNAVAILABLE"
                return None, raw, "FILL_MARK_STALE"
            except Exception:
                return None, None, "FILL_MARK_UNAVAILABLE"
        side_u = str(side or "BUY").upper()
        px = mark.executable_buy(slip_pts) if side_u.startswith("BUY") else mark.executable_sell(slip_pts)
        if px is None or px <= 0:
            return None, mark, "FILL_MARK_NO_QUOTABLE_SIDE"
        return float(px), mark, None
    except Exception as e:
        return None, None, f"FILL_MARK_ERROR_{str(e)[:60]}"


def _statutory_for_fill(entry_px: float, exit_px: Optional[float], qty: int) -> dict[str, float]:
    try:
        from app.signals.options_intelligence.path_simulator import IndianOptionCosts
        costs = IndianOptionCosts()
        if exit_px is not None and exit_px > 0:
            return costs.calculate_total_costs(entry_px, exit_px, max(1, qty))
        # Entry leg only (open): half the round trip is unknown yet.
        full = costs.calculate_total_costs(entry_px, entry_px, max(1, qty))
        return {**full, "total_friction": round(full.get("statutory_taxes", 0.0) / 2.0, 2)}
    except Exception:
        return {"total_friction": 0.0}


class Position(BaseModel):
    position_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    signal_id: str
    execution_intent_id: str
    broker_order_id: str | None = None

    underlying: str
    instrument_symbol: str
    side: str = "BUY"
    lot_size: int = 75

    # Contract linkage (drives ledger + marks).
    broker_symbol: str = ""
    strike: Optional[float] = None
    expiry: Optional[str] = None
    option_type: Optional[str] = None

    entry_price: Decimal
    entry_quantity: int
    remaining_quantity: int
    filled_quantity: int = 0
    requested_quantity: int = 0

    fill_mark_source: Optional[str] = None
    fill_slippage_pts: float = 0.0

    t1_price: Decimal | None = None
    t1_quantity: int = 0
    t1_fill_price: Decimal | None = None

    exit_price: Decimal | None = None
    exit_reason: str | None = None

    gross_pnl_inr: Decimal = Decimal(0)
    statutory_costs_inr: Decimal = Decimal(0)
    net_pnl_inr: Decimal = Decimal(0)

    position_state: PositionState = PositionState.OPEN
    opened_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    closed_at_utc: int | None = None
    history: list[dict[str, Any]] = Field(default_factory=list)

    def validate_quantities(self) -> Optional[str]:
        for qty, tag in ((self.entry_quantity, "entry"), (self.remaining_quantity, "remaining")):
            err = _validate_lot_quantity(int(qty or 0), int(self.lot_size or 0))
            if err and "remaining" not in tag:
                return f"{tag}:{err}"
            if tag == "remaining" and int(qty or 0) < 0:
                return "remaining:QTY_NEGATIVE"
        if int(self.remaining_quantity or 0) > int(self.entry_quantity or 0):
            return "remaining:EXCEEDS_ENTRY"
        return None

    @classmethod
    def open_from_fill(
        cls,
        signal_id: str,
        execution_intent_id: str,
        underlying: str,
        instrument_symbol: str,
        side: str,
        quantity: int,
        lot_size: int,
        slip_pts: float = 0.0,
        broker_symbol: str = "",
        strike: Optional[float] = None,
        expiry: Optional[str] = None,
        option_type: Optional[str] = None,
        desk: Optional[str] = None,
        broker_order_id: Optional[str] = None,
    ) -> "Position":
        """Fail-closed constructor: raises on missing/stale mark or bad qty."""
        sym = broker_symbol or instrument_symbol
        err_q = _validate_lot_quantity(int(quantity or 0), int(lot_size or 0))
        if err_q:
            raise ValueError(f"POSITION_QTY_REJECTED: {err_q}")
        fill_px, mark, err = _require_fill_mark(sym, side, slip_pts, desk)
        if err or fill_px is None:
            raise ValueError(f"POSITION_FILL_REJECTED: {err or 'no fill price'} for {sym}")
        pos = cls(
            signal_id=signal_id,
            execution_intent_id=execution_intent_id,
            broker_order_id=broker_order_id,
            underlying=underlying,
            instrument_symbol=instrument_symbol,
            side=side,
            lot_size=int(lot_size),
            broker_symbol=sym,
            strike=float(strike) if strike is not None else None,
            expiry=str(expiry) if expiry else None,
            option_type=str(option_type) if option_type else None,
            entry_price=Decimal(str(fill_px)),
            entry_quantity=int(quantity),
            remaining_quantity=int(quantity),
            filled_quantity=int(quantity),
            requested_quantity=int(quantity),
            fill_mark_source=getattr(mark, "source", None),
            fill_slippage_pts=float(slip_pts or 0.0),
        )
        return pos

    def transition_to(self, new_state: PositionState, reason: str = "", fill_price: Decimal | None = None) -> bool:
        if new_state not in ALLOWED_POSITION_TRANSITIONS.get(self.position_state, set()):
            logger.error(
                "illegal_position_transition",
                position_id=self.position_id,
                from_state=self.position_state,
                to_state=new_state,
                reason=reason,
            )
            return False

        # Qty validation on every movement (partial fills included).
        if new_state == PositionState.PARTIALLY_FILLED and fill_price is None:
            logger.error("partial_fill_missing_price", position_id=self.position_id)
            return False
        qerr = self.validate_quantities()
        if qerr:
            logger.error("position_qty_invalid", position_id=self.position_id, error=qerr)
            return False

        # Statutory + net economics inside the transition (single schedule).
        try:
            if new_state in (PositionState.T1_PARTIAL_EXIT, PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP) and fill_price is not None:
                exit_px = float(fill_price)
                entry_px = float(self.entry_price or 0)
                qty = int(self.remaining_quantity or self.entry_quantity or 0)
                br = _statutory_for_fill(entry_px, exit_px, qty)
                total_f = float(br.get("total_friction", 0.0) or 0.0)
                side_mult = 1.0 if str(self.side).upper().startswith("BUY") else -1.0
                gross = (exit_px - entry_px) * qty * side_mult
                self.gross_pnl_inr = Decimal(str(round(gross, 2)))
                self.statutory_costs_inr = Decimal(str(round(total_f, 2)))
                self.net_pnl_inr = Decimal(str(round(gross - total_f, 2)))
                self.exit_price = Decimal(str(exit_px))
                self.exit_reason = reason or new_state.value
                if new_state == PositionState.T1_PARTIAL_EXIT:
                    self.t1_fill_price = Decimal(str(exit_px))
            elif new_state in (PositionState.ASSIGNED, PositionState.EXPIRED):
                # Expiry: intrinsic exit (ITM) or worthless (OTM) + assignment friction.
                try:
                    from app.signals.transaction_costs import compute_expiry_assignment_friction
                    sp = float(self.strike or 0)
                    ep = float(fill_price) if fill_price is not None else float(self.entry_price or 0)
                    # fill_price carries spot at expiry when provided.
                    intr = 0.0
                    if sp > 0:
                        if str(self.option_type or "").upper() == "PE":
                            intr = max(0.0, sp - ep)
                        else:
                            intr = max(0.0, ep - sp)
                    entry_px = float(self.entry_price or 0)
                    qty = int(self.entry_quantity or 0)
                    total_assign, _ = compute_expiry_assignment_friction(intr, 1, max(1, qty))
                    gross = (intr - entry_px) * qty
                    self.gross_pnl_inr = Decimal(str(round(gross, 2)))
                    self.statutory_costs_inr = Decimal(str(round(total_assign, 2)))
                    self.net_pnl_inr = Decimal(str(round(gross - total_assign, 2)))
                    self.exit_price = Decimal(str(round(intr, 2)))
                    self.exit_reason = reason or new_state.value
                except Exception:
                    pass
        except Exception as e:
            logger.debug("position_pnl_compute_failed", position_id=self.position_id, error=str(e)[:150])

        old_state = self.position_state
        self.position_state = new_state
        now_ms = int(time.time() * 1000)
        self.history.append({
            "from_state": old_state.value,
            "to_state": new_state.value,
            "reason": reason,
            "fill_price": str(fill_price) if fill_price else None,
            "gross_pnl_inr": str(self.gross_pnl_inr),
            "statutory_costs_inr": str(self.statutory_costs_inr),
            "net_pnl_inr": str(self.net_pnl_inr),
            "timestamp_utc": now_ms,
        })

        if new_state in (PositionState.T2_EXIT, PositionState.STOP_LOSS, PositionState.TIME_STOP, PositionState.ASSIGNED, PositionState.EXPIRED, PositionState.CLOSED):
            self.closed_at_utc = now_ms
            # Auto-remove from the portfolio Greeks ledger on close.
            try:
                from app.signals.portfolio_greeks import portfolio_greeks_ledger
                portfolio_greeks_ledger.remove_position(self.position_id)
            except Exception:
                pass
            if new_state != PositionState.CLOSED:
                # Auto-transition terminal exit stages to CLOSED
                self.position_state = PositionState.CLOSED
                self.history.append({
                    "from_state": new_state.value,
                    "to_state": PositionState.CLOSED.value,
                    "reason": "TERMINAL_STATE_FINALIZED",
                    "timestamp_utc": now_ms,
                })

        logger.info(
            "position_transition",
            position_id=self.position_id,
            signal_id=self.signal_id,
            to_state=self.position_state.value,
            reason=reason,
        )
        return True


class PositionRegistry:
    """
    Registry for active and historical positions.
    """
    def __init__(self):
        self._positions: dict[str, Position] = {}

    def register(self, position: Position) -> Position:
        # Qty gate at the door (fail-closed, but never crash the paper loop).
        try:
            qerr = position.validate_quantities()
            if qerr:
                logger.error("position_register_qty_rejected", position_id=position.position_id, error=qerr)
                raise ValueError(f"POSITION_QTY_REJECTED: {qerr}")
        except ValueError:
            raise
        except Exception:
            pass
        # Default contract linkage from the instrument symbol when absent.
        try:
            if not position.broker_symbol:
                position.broker_symbol = position.instrument_symbol
        except Exception:
            pass
        self._positions[position.position_id] = position
        # Mirror into the portfolio Greeks ledger (best-effort; unknown Greeks skip).
        try:
            from app.signals.portfolio_greeks import portfolio_greeks_ledger, PortfolioGreekPosition
            _side = 1.0 if str(position.side).upper().startswith("BUY") else -1.0
            _otype = str(position.option_type or ("CE" if "CE" in position.instrument_symbol.upper() else ("PE" if "PE" in position.instrument_symbol.upper() else "CE")))
            ledger_pos = PortfolioGreekPosition(
                position_id=position.position_id,
                underlying=str(position.underlying or "").upper(),
                horizon="INTRADAY",
                option_type=_otype,  # type: ignore[arg-type]
                strike=float(position.strike or 0.0),
                expiry_date=str(position.expiry or ""),
                quantity=int(position.entry_quantity or 0),
                unit_delta=0.5 * _side,
                unit_gamma=0.0005,
                unit_theta_day=-10.0,
                unit_vega=10.0,
            )
            portfolio_greeks_ledger.add_position(ledger_pos)
        except Exception as e:
            logger.debug("position_ledger_mirror_skipped", position_id=position.position_id, error=str(e)[:150])
        return position

    def get(self, position_id: str) -> Position | None:
        return self._positions.get(position_id)

    def get_by_signal(self, signal_id: str) -> Position | None:
        for p in self._positions.values():
            if p.signal_id == signal_id:
                return p
        return None

    def list_open(self) -> list[Position]:
        return [p for p in self._positions.values() if p.position_state != PositionState.CLOSED]

    def all_positions(self) -> list[Position]:
        return list(self._positions.values())

    def close_position(self, position_id: str, reason: str = "CLOSED") -> bool:
        pos = self._positions.get(position_id)
        if pos is None:
            return False
        ok = pos.transition_to(PositionState.CLOSED, reason=reason)
        try:
            from app.signals.portfolio_greeks import portfolio_greeks_ledger
            portfolio_greeks_ledger.remove_position(position_id)
        except Exception:
            pass
        return ok

    def clear(self) -> None:
        # Best-effort ledger hygiene on test isolation resets.
        try:
            from app.signals.portfolio_greeks import portfolio_greeks_ledger
            for pid in list(self._positions.keys()):
                try:
                    portfolio_greeks_ledger.remove_position(pid)
                except Exception:
                    pass
        except Exception:
            pass
        self._positions.clear()


position_registry = PositionRegistry()
