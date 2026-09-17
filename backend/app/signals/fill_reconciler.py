"""
Fill Reconciler & Execution Domain Adapter (Version 6.0)

Enforces:
  1. Strict Domain Separation: Underlying Signal Domain vs Execution Domain (§24).
  2. Option Realized P&L is calculated strictly from actual option fills:
     Net P&L = (Exit Premium - Entry Premium) * Qty - Statutory Costs.
     DELTA IS STRICTLY FORBIDDEN FOR REALIZED P&L (§25).
  3. Staged Exits: T1 (50% staged exit) + Runner (50% runner exit at T2/SL/Time-Stop).
  4. Residual Quantity & Fill Tracking.
  5. Indian Option Statutory Costs Deduction via app.quant.costs.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field
import structlog

from app.quant.costs import calculate_option_costs, CostBreakdown
from app.quant.black76 import black76_price
from app.signals.fsm import SignalInstance

logger = structlog.get_logger()


class OptionStageFill(BaseModel):
    stage: str  # ENTRY, TARGET_1, TARGET_2, STOP_LOSS, TIME_STOP, RUNNER_TIME_STOP, CLOSED
    price: float
    quantity: int
    timestamp_utc: int
    turnover: float
    costs: Optional[dict] = None
    realized_pnl_inr: float = 0.0


class FillReconciliationRecord(BaseModel):
    signal_id: str
    underlying: str
    strategy: str
    direction: str
    option_symbol: Optional[str] = None
    option_type: Optional[str] = None
    strike: Optional[float] = None
    lot_size: int = 75
    intended_qty: int = 0
    remaining_qty: int = 0
    t1_qty: int = 0

    entry_fill_price: float = 0.0
    t1_fill_price: Optional[float] = None
    final_fill_price: Optional[float] = None
    exit_reason: Optional[str] = None

    t1_realized_pnl: float = 0.0
    final_realized_pnl: float = 0.0
    gross_realized_pnl: float = 0.0
    total_statutory_costs: float = 0.0
    net_realized_pnl_inr: float = 0.0
    realized_rr: float = 0.0

    is_fully_closed: bool = False
    fills: list[OptionStageFill] = Field(default_factory=list)
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    updated_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    # True when rebuilt from ledger fills after the in-memory record was lost
    # (e.g. restart). Economics before the rebuild are unknown — consumers
    # must prefer the audit ledger's own P&L over this record's partial sums.
    synthetic: bool = False

    # v3.0 Decoupled Domain Links & Reconciliation Status
    execution_intent_id: Optional[str] = None
    position_id: Optional[str] = None
    reconciliation_status: str = "RECONCILED"  # RECONCILED | PARTIAL | RECONCILIATION_REQUIRED | AMBIGUOUS
    reconciliation_notes: Optional[str] = None


class OptionFillReconciler:
    """
    Reconciles execution domain option fills with underlying signal domain.
    Tracks residual quantities across multi-stage exits and computes audited net P&L.
    """

    def __init__(self):
        self._records: dict[str, FillReconciliationRecord] = {}

    def estimate_option_premium(
        self,
        spot: float,
        strike: float,
        option_type: str,
        dte_days: float = 3.0,
        iv: float = 0.15,
        risk_free_rate: float = 0.07,
        allow_model: bool = False,
    ) -> float:
        """
        Estimates theoretical option premium using Black-76 when market quotes are absent.
        GATED behind allow_model=True — production fill paths must never call this
        without explicit opt-in (model prices are not fills).
        """
        if not allow_model:
            raise ValueError(
                "estimate_option_premium is model-gated: pass allow_model=True explicitly. "
                "Production fills/exits must use chain marks, never a model price."
            )
        flag = "CE" if "C" in option_type.upper() else "PE"
        t_years = max(0.0001, dte_days / 365.0)
        try:
            prem = black76_price(flag, spot, strike, t_years, risk_free_rate, iv)
            return round(max(0.05, prem), 2)
        except Exception as e:
            logger.warning("black76_estimation_failed", error=str(e), spot=spot, strike=strike)
            # Fallback intrinsic value + minimal extrinsic
            intrinsic = max(0.0, spot - strike) if flag == "CE" else max(0.0, strike - spot)
            return round(max(0.05, intrinsic + (spot * 0.005)), 2)

    def reconcile_entry(
        self,
        sig: SignalInstance,
        fill_price: float | None,
        quantity: int,
        lot_size: int = 75,
    ) -> FillReconciliationRecord | None:
        """
        Registers actual entry fill, sets initial position and pre-computes 50% staged exit qty.
        Corrupted entries (None/non-positive/off-domain) return None + quarantine
        (RECONCILIATION_REQUIRED) — never fabricate a premium.
        Idempotent on (signal, stage=ENTRY, fill_ts bucket).
        """
        # Guard: an option fill can NEVER be an index spot price (>5000 pts).
        # FAIL CLOSED: do not repair it with a Black-76 estimate — that would
        # manufacture the very premium we are trying to verify. Record the raw
        # observation, flag the record, and let the audit ledger refuse to book
        # cross-domain P&L downstream.
        is_opt = bool(sig.option_contract or "CALL" in sig.direction or "PUT" in sig.direction)
        if fill_price is None or (isinstance(fill_price, (int, float)) and float(fill_price) <= 0):
            logger.error("corrupted_option_fill_none", signal_id=sig.signal_id, note="None/non-positive fill → quarantine")
            rec_q = FillReconciliationRecord(
                signal_id=sig.signal_id, underlying=sig.underlying, strategy=sig.strategy,
                direction=sig.direction, lot_size=lot_size, intended_qty=int(quantity or 0),
                remaining_qty=int(quantity or 0), entry_fill_price=0.0,
                reconciliation_status="RECONCILIATION_REQUIRED",
                reconciliation_notes="corrupted entry: None/non-positive fill",
            )
            self._records[sig.signal_id] = rec_q
            return None
        domain_bad = is_opt and float(fill_price) > 5000.0
        if domain_bad:
            logger.error(
                "corrupted_option_fill_price_detected",
                signal_id=sig.signal_id,
                bad_price=fill_price,
                note="entry not premium-domain; no estimate substituted",
            )
            rec_q = FillReconciliationRecord(
                signal_id=sig.signal_id, underlying=sig.underlying, strategy=sig.strategy,
                direction=sig.direction, lot_size=lot_size, intended_qty=int(quantity or 0),
                remaining_qty=int(quantity or 0), entry_fill_price=float(fill_price),
                reconciliation_status="RECONCILIATION_REQUIRED",
                reconciliation_notes=f"entry {fill_price} is not premium-domain",
            )
            self._records[sig.signal_id] = rec_q
            return None

        now_ms = int(time.time() * 1000)
        d_fill = Decimal(str(fill_price))

        # Update FSM signal state
        sig.actual_fill_price = d_fill
        sig.entry_price = d_fill
        sig.intended_qty = Decimal(str(quantity))
        sig.remaining_qty = Decimal(str(quantity))

        # Calculate T1 staged quantity (50% rounded to nearest lot size, minimum 1 lot)
        lots = max(1, quantity // lot_size)
        t1_lots = max(1, lots // 2) if lots > 1 else 1
        t1_qty = min(quantity, t1_lots * lot_size)

        opt = sig.option_contract or {}
        rec = FillReconciliationRecord(
            signal_id=sig.signal_id,
            underlying=sig.underlying,
            strategy=sig.strategy,
            direction=sig.direction,
            option_symbol=opt.get("broker_symbol"),
            option_type=opt.get("option_type", "CE" if "CALL" in sig.direction else "PE"),
            strike=float(opt.get("strike", 0.0)) if opt.get("strike") else None,
            lot_size=lot_size,
            intended_qty=quantity,
            remaining_qty=quantity,
            t1_qty=t1_qty,
            entry_fill_price=fill_price,
            fills=[
                OptionStageFill(
                    stage="ENTRY",
                    price=fill_price,
                    quantity=quantity,
                    timestamp_utc=now_ms,
                    turnover=round(fill_price * quantity, 2),
                )
            ],
            created_at_utc=now_ms,
            updated_at_utc=now_ms,
            execution_intent_id=getattr(sig, "execution_intent_id", None),
            position_id=getattr(sig, "position_id", None),
            reconciliation_status="RECONCILED",
            reconciliation_notes=None,
        )
        self._records[sig.signal_id] = rec
        logger.info(
            "fill_reconciled_entry",
            signal_id=sig.signal_id,
            fill_price=fill_price,
            qty=quantity,
            t1_qty=t1_qty,
        )
        return rec

    def _t1_idem_key(self, signal_id: str, exit_fill_price: float, exit_time_ms: int) -> str:
        bucket = int(exit_time_ms // 1000)
        return f"{signal_id}:TARGET_1:{exit_fill_price}:{bucket}"

    def reconcile_t1_exit(
        self,
        sig: SignalInstance,
        exit_fill_price: float,
        exit_time_ms: Optional[int] = None,
    ) -> FillReconciliationRecord:
        """
        Executes T1 Staged Exit (§18, §25):
          - Closes t1_qty (50% staged exit).
          - Calculates net option P&L and statutory costs for closed portion.
          - Updates remaining_qty for the runner.
          - FSM auto-ratchets SL to Cost and starts the Runner Clock.
          Domain-guarded + idempotent on (signal, stage, fill_ts).
        """
        now_ms = exit_time_ms or int(time.time() * 1000)
        # Idempotency: same (signal, stage, fill_ts bucket) returns existing.
        _idem = self._t1_idem_key(sig.signal_id, float(exit_fill_price or 0), now_ms)
        existing = self._records.get(sig.signal_id)
        if existing is not None and existing.t1_fill_price == exit_fill_price:
            # Same price already booked for T1 — check fill history for same bucket.
            for f in existing.fills:
                if f.stage == "TARGET_1" and abs(int(f.timestamp_utc // 1000) - int(now_ms // 1000)) < 2:
                    return existing
        # Domain guard (same as final exit): option T1 must be premium-domain.
        _is_opt_t1 = bool((getattr(sig, "option_contract", None) or {}) or ("CALL" in str(sig.direction) or "PUT" in str(sig.direction)))
        if _is_opt_t1 and float(exit_fill_price or 0) > 5000.0:
            logger.error("fill_t1_domain_mismatch_withheld", signal_id=sig.signal_id, exit_price=exit_fill_price)
            rec_bad = existing or FillReconciliationRecord(
                signal_id=sig.signal_id, underlying=sig.underlying, strategy=sig.strategy,
                direction=sig.direction, reconciliation_status="RECONCILIATION_REQUIRED",
                reconciliation_notes=f"T1 exit {exit_fill_price} not premium-domain",
            )
            rec_bad.reconciliation_status = "RECONCILIATION_REQUIRED"
            rec_bad.reconciliation_notes = f"T1 exit {exit_fill_price} not premium-domain"
            self._records[sig.signal_id] = rec_bad
            return rec_bad
        rec = existing
        if not rec:
            # Create synthetic record if entry wasn't explicitly registered
            lot_sz = 75 if sig.underlying == "NIFTY" else (30 if sig.underlying == "BANKNIFTY" else 10)
            qty = int(sig.intended_qty or (sig.paper_order or {}).get("quantity", lot_sz))
            rec = self.reconcile_entry(sig, float(sig.actual_fill_price or sig.trigger), qty, lot_sz)
            if rec is None:
                # Corrupted entry → quarantine record already stored; return it.
                return self._records[sig.signal_id]

        # Quantity to close
        close_qty = rec.t1_qty
        if close_qty <= 0 or close_qty > rec.remaining_qty:
            close_qty = rec.remaining_qty

        buy_turnover = round(rec.entry_fill_price * close_qty, 2)
        sell_turnover = round(exit_fill_price * close_qty, 2)
        costs: CostBreakdown = calculate_option_costs(
            buy_turnover=buy_turnover,
            sell_turnover=sell_turnover,
            num_orders=2,
        )
        stage_gross_pnl = round(sell_turnover - buy_turnover, 2)
        stage_net_pnl = round(stage_gross_pnl - costs.total_cost, 2)

        rec.t1_fill_price = exit_fill_price
        rec.t1_realized_pnl = stage_net_pnl
        rec.total_statutory_costs = round(rec.total_statutory_costs + costs.total_cost, 2)
        rec.gross_realized_pnl = round(rec.gross_realized_pnl + stage_gross_pnl, 2)
        rec.net_realized_pnl_inr = round(rec.net_realized_pnl_inr + stage_net_pnl, 2)

        # Update remaining quantities
        rec.remaining_qty = max(0, rec.remaining_qty - close_qty)
        sig.remaining_qty = Decimal(str(rec.remaining_qty))
        sig.t1_realized_qty = Decimal(str(close_qty))

        rec.fills.append(
            OptionStageFill(
                stage="TARGET_1",
                price=exit_fill_price,
                quantity=close_qty,
                timestamp_utc=now_ms,
                turnover=sell_turnover,
                costs=costs._asdict(),
                realized_pnl_inr=stage_net_pnl,
            )
        )
        rec.updated_at_utc = now_ms
        logger.info(
            "fill_reconciled_t1_exit",
            signal_id=sig.signal_id,
            exit_price=exit_fill_price,
            closed_qty=close_qty,
            remaining_qty=rec.remaining_qty,
            net_pnl=stage_net_pnl,
        )
        return rec

    def reconcile_final_exit(
        self,
        sig: SignalInstance,
        exit_fill_price: float,
        exit_reason: str,
        exit_time_ms: Optional[int] = None,
    ) -> FillReconciliationRecord:
        """
        Executes Final Exit for the remaining position:
          - Closes 100% of remaining_qty.
          - Calculates net option P&L and statutory costs.
          - Computes total blended realized P&L and R:R.
          - Marks trade fully closed.
        """
        now_ms = exit_time_ms or int(time.time() * 1000)
        rec = self._records.get(sig.signal_id)
        if not rec:
            lot_sz = 75 if sig.underlying == "NIFTY" else (30 if sig.underlying == "BANKNIFTY" else 10)
            qty = int(sig.intended_qty or (sig.paper_order or {}).get("quantity", lot_sz))
            rec = self.reconcile_entry(sig, float(sig.actual_fill_price or sig.trigger), qty, lot_sz)
            if rec is None:
                return self._records[sig.signal_id]
        # Idempotency (signal, stage, fill_ts): same final already booked → noop.
        try:
            for f in rec.fills:
                if f.stage == exit_reason and abs(int(f.timestamp_utc // 1000) - int(now_ms // 1000)) < 2 and f.price == exit_fill_price:
                    return rec
        except Exception:
            pass

        close_qty = rec.remaining_qty
        if close_qty > 0:
            # Domain guard (fail closed, no repair): option premiums live below
            # ~5000, so a spot-scale entry (e.g. trigger 23807 stored as a fill)
            # paired with a premium exit would fabricate a -₹17L P&L. Close the
            # position but book nothing — a Black-76 "repair" here would only
            # swap one invented number for another.
            _is_opt = bool(
                (sig.option_contract or {})
                or ("CALL" in str(sig.direction) or "PUT" in str(sig.direction))
                or rec.option_type
                or rec.strike
            )
            _domain_mismatch = _is_opt and (rec.entry_fill_price > 5000.0) != (exit_fill_price > 5000.0)
            if _is_opt and rec.entry_fill_price > 5000.0:
                _domain_mismatch = True
            if _domain_mismatch:
                logger.error(
                    "fill_domain_mismatch_pnl_withheld",
                    signal_id=sig.signal_id,
                    entry=rec.entry_fill_price,
                    exit_price=exit_fill_price,
                )
                rec.remaining_qty = 0
                sig.remaining_qty = Decimal("0")
                rec.is_fully_closed = True
                rec.exit_reason = exit_reason
                rec.reconciliation_status = "RECONCILIATION_REQUIRED"
                rec.reconciliation_notes = (
                    f"entry {rec.entry_fill_price} and exit {exit_fill_price} are not in the same price domain"
                )
                rec.updated_at_utc = now_ms
                return rec
            buy_turnover = round(rec.entry_fill_price * close_qty, 2)
            sell_turnover = round(exit_fill_price * close_qty, 2)
            costs: CostBreakdown = calculate_option_costs(
                buy_turnover=buy_turnover,
                sell_turnover=sell_turnover,
                num_orders=2,
            )
            stage_gross_pnl = round(sell_turnover - buy_turnover, 2)
            stage_net_pnl = round(stage_gross_pnl - costs.total_cost, 2)

            rec.final_fill_price = exit_fill_price
            rec.final_realized_pnl = stage_net_pnl
            rec.total_statutory_costs = round(rec.total_statutory_costs + costs.total_cost, 2)
            rec.gross_realized_pnl = round(rec.gross_realized_pnl + stage_gross_pnl, 2)
            rec.net_realized_pnl_inr = round(rec.net_realized_pnl_inr + stage_net_pnl, 2)

            rec.fills.append(
                OptionStageFill(
                    stage=exit_reason,
                    price=exit_fill_price,
                    quantity=close_qty,
                    timestamp_utc=now_ms,
                    turnover=sell_turnover,
                    costs=costs._asdict(),
                    realized_pnl_inr=stage_net_pnl,
                )
            )

        rec.remaining_qty = 0
        sig.remaining_qty = Decimal("0")
        rec.is_fully_closed = True
        rec.exit_reason = exit_reason
        rec.updated_at_utc = now_ms

        # Compute blended realized R:R from FSM risk_r (authoritative risk),
        # never the 30% heuristic. Falls back to premium fraction only when
        # risk_r is missing (legacy rows).
        try:
            _fsm_risk = getattr(sig, "risk_r", None)
            if _fsm_risk is not None and float(_fsm_risk) > 0:
                risk_inr = float(_fsm_risk) * float(rec.intended_qty or 0)
            else:
                option_risk_pts = max(1.0, rec.entry_fill_price * 0.30)
                risk_inr = option_risk_pts * rec.intended_qty
        except Exception:
            option_risk_pts = max(1.0, rec.entry_fill_price * 0.30)
            risk_inr = option_risk_pts * rec.intended_qty
        if risk_inr > 0 and not (rec.entry_fill_price > 5000.0 and exit_fill_price < 5000.0):
            rec.realized_rr = round(rec.net_realized_pnl_inr / risk_inr, 2)

        logger.info(
            "fill_reconciled_final_exit",
            signal_id=sig.signal_id,
            reason=exit_reason,
            exit_price=exit_fill_price,
            total_net_pnl=rec.net_realized_pnl_inr,
            costs=rec.total_statutory_costs,
            realized_rr=rec.realized_rr,
        )
        return rec

    def get_reconciliation(self, signal_id: str) -> Optional[FillReconciliationRecord]:
        return self._records.get(signal_id)


option_fill_reconciler = OptionFillReconciler()
