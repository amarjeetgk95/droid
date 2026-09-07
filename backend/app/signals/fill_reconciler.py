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
    ) -> float:
        """
        Estimates theoretical option premium using Black-76 when market quotes are absent.
        """
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
        fill_price: float,
        quantity: int,
        lot_size: int = 75,
    ) -> FillReconciliationRecord:
        """
        Registers actual entry fill, sets initial position and pre-computes 50% staged exit qty.
        """
        # Guard: Option fill price can NEVER be an index spot price (>5000 pts)
        is_opt = bool(sig.option_contract or "CALL" in sig.direction or "PUT" in sig.direction)
        if is_opt and fill_price > 5000.0:
            logger.error("corrupted_option_fill_price_detected", signal_id=sig.signal_id, bad_price=fill_price)
            strike = float((sig.option_contract or {}).get("strike", 0.0)) or float(sig.spot_price or sig.trigger)
            opt_type = (sig.option_contract or {}).get("option_type", "CE" if "CALL" in sig.direction else "PE")
            fill_price = self.estimate_option_premium(float(sig.spot_price or sig.trigger), strike, opt_type)
            logger.info("reconcile_entry_clamped_to_estimate", signal_id=sig.signal_id, estimated_price=fill_price)

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
        """
        now_ms = exit_time_ms or int(time.time() * 1000)
        rec = self._records.get(sig.signal_id)
        if not rec:
            # Create synthetic record if entry wasn't explicitly registered
            lot_sz = 75 if sig.underlying == "NIFTY" else (30 if sig.underlying == "BANKNIFTY" else 10)
            qty = int(sig.intended_qty or (sig.paper_order or {}).get("quantity", lot_sz))
            rec = self.reconcile_entry(sig, float(sig.actual_fill_price or sig.trigger), qty, lot_sz)

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

        close_qty = rec.remaining_qty
        if close_qty > 0:
            # Domain repair: option premiums live below ~5000. A spot-scale
            # entry (e.g. trigger 23807 stored as fill) paired with a premium
            # exit (132.98) fabricates a -₹17L P&L. Repair via Black76
            # estimate; if unrepairable, close the position without poisoning
            # P&L with cross-domain garbage.
            _is_opt = bool(
                (sig.option_contract or {})
                or ("CALL" in str(sig.direction) or "PUT" in str(sig.direction))
                or rec.option_type
                or rec.strike
            )
            if _is_opt and rec.entry_fill_price > 5000.0 and exit_fill_price < 5000.0:
                _repaired: Optional[float] = None
                try:
                    _opt = sig.option_contract or {}
                    _strike = float(_opt.get("strike") or rec.strike or 0.0)
                    _otype = str(_opt.get("option_type") or rec.option_type or ("CE" if "CALL" in str(sig.direction) else "PE"))
                    _spot = float(sig.spot_price or sig.trigger or 0.0)
                    if _strike > 0 and _spot > 0:
                        _repaired = self.estimate_option_premium(spot=_spot, strike=_strike, option_type=_otype)
                except Exception:
                    _repaired = None
                if _repaired and _repaired < 5000.0:
                    logger.warning(
                        "fill_entry_spot_scale_repaired",
                        signal_id=sig.signal_id,
                        bad_entry=rec.entry_fill_price,
                        repaired=_repaired,
                    )
                    rec.entry_fill_price = _repaired
                else:
                    logger.error(
                        "fill_entry_spot_scale_unrepairable_hold_pnl",
                        signal_id=sig.signal_id,
                        entry=rec.entry_fill_price,
                        exit_price=exit_fill_price,
                    )
                    rec.remaining_qty = 0
                    sig.remaining_qty = Decimal("0")
                    rec.is_fully_closed = True
                    rec.exit_reason = exit_reason
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

        # Compute blended realized R:R (premium-domain only; a spot-scale
        # entry here means the repair above was bypassed — skip R, keep P&L).
        # R = initial risk in INR = (entry_fill_price - stop_loss) * intended_qty
        option_risk_pts = max(1.0, rec.entry_fill_price * 0.30)  # default 30% option stop if not explicit
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
