"""
Crypto Fill Reconciler & Staged Execution Domain Adapter — §18, §24, §25
Enforces:
  1. Strict Domain Separation: Underlying spot/futures index level vs. Execution fill prices.
  2. Staged Partial Exits: Target 1 (50% booked) + Runner (remaining 50% to Target 2 / BE / Time-Stop).
  3. Realistic Crypto Friction: Binance Futures VIP0 (0.05% taker, 0.02% maker) + 2 bps slippage.
  4. Realized Net R-Multiple: computed strictly from actual fills after all exchange fees.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel, Field
import structlog

from app.crypto_scalp.fsm import CryptoSignalInstance

logger = structlog.get_logger()

TAKER_FEE_RATE = 0.0005  # 0.05% (Binance Futures VIP0 taker)
MAKER_FEE_RATE = 0.0002  # 0.02%
SLIPPAGE_BPS_RATE = 0.0002  # 2 bps slippage model


class CryptoStageFill(BaseModel):
    stage: str  # ENTRY, TARGET_1, TARGET_2, STOP_LOSS, BREAKEVEN_STOP, TIME_STOP, RUNNER_TIME_STOP
    price: float
    quantity: float
    timestamp_utc: int
    notional_usd: float
    fee_usd: float
    slippage_usd: float
    gross_pnl_usd: float = 0.0
    net_pnl_usd: float = 0.0


class CryptoFillReconciliationRecord(BaseModel):
    signal_id: str
    symbol: str
    direction: str
    strategy: str

    entry_fill_price: float = 0.0
    initial_qty: float = 0.0
    t1_qty: float = 0.0
    remaining_qty: float = 0.0
    initial_risk_usd: float = 0.0

    t1_fill_price: Optional[float] = None
    final_fill_price: Optional[float] = None
    exit_reason: Optional[str] = None

    t1_gross_pnl_usd: float = 0.0
    t1_net_pnl_usd: float = 0.0
    final_gross_pnl_usd: float = 0.0
    final_net_pnl_usd: float = 0.0

    total_gross_pnl_usd: float = 0.0
    total_fees_usd: float = 0.0
    total_slippage_usd: float = 0.0
    total_net_pnl_usd: float = 0.0
    realized_rr_gross: float = 0.0
    realized_rr_net: float = 0.0

    is_fully_closed: bool = False
    fills: list[CryptoStageFill] = Field(default_factory=list)
    created_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))
    updated_at_utc: int = Field(default_factory=lambda: int(time.time() * 1000))


class CryptoFillReconciler:
    """
    Manages multi-stage crypto fills, residual quantities, exchange fees, and audited net P&L.
    """

    def __init__(self):
        self._records: dict[str, CryptoFillReconciliationRecord] = {}

    def reconcile_entry(
        self,
        sig: CryptoSignalInstance,
        fill_price: float,
        quantity: float,
    ) -> CryptoFillReconciliationRecord:
        """Register entry fill, deduct entry taker fee, set initial 50% staged exit qty."""
        now_ms = int(time.time() * 1000)
        d_fill = Decimal(str(fill_price))

        sig.actual_fill_price = d_fill
        sig.entry_price = d_fill
        sig.intended_qty = Decimal(str(quantity))
        sig.remaining_qty = Decimal(str(quantity))

        # 50% staged exit rounded to 3 decimal places
        t1_qty = round(quantity * 0.50, 4)
        if t1_qty <= 0:
            t1_qty = quantity

        notional_entry = round(fill_price * quantity, 2)
        fee_entry = round(notional_entry * TAKER_FEE_RATE, 4)
        slip_entry = round(notional_entry * SLIPPAGE_BPS_RATE, 4)

        risk_pts = float(abs(sig.trigger - sig.stop_loss)) if sig.trigger and sig.stop_loss else 0.0
        initial_risk_usd = round(quantity * risk_pts, 2)

        rec = CryptoFillReconciliationRecord(
            signal_id=sig.signal_id,
            symbol=sig.symbol,
            direction=sig.direction,
            strategy=sig.strategy,
            entry_fill_price=fill_price,
            initial_qty=quantity,
            t1_qty=t1_qty,
            remaining_qty=quantity,
            initial_risk_usd=initial_risk_usd,
            total_fees_usd=fee_entry,
            total_slippage_usd=slip_entry,
            total_net_pnl_usd=-fee_entry,
            fills=[
                CryptoStageFill(
                    stage="ENTRY",
                    price=fill_price,
                    quantity=quantity,
                    timestamp_utc=now_ms,
                    notional_usd=notional_entry,
                    fee_usd=fee_entry,
                    slippage_usd=slip_entry,
                    gross_pnl_usd=0.0,
                    net_pnl_usd=-fee_entry,
                )
            ],
            created_at_utc=now_ms,
            updated_at_utc=now_ms,
        )
        self._records[sig.signal_id] = rec
        logger.info(
            "crypto_fill_reconciled_entry",
            signal_id=sig.signal_id,
            symbol=sig.symbol,
            fill_price=fill_price,
            qty=quantity,
            t1_qty=t1_qty,
        )
        return rec

    def reconcile_t1_exit(
        self,
        sig: CryptoSignalInstance,
        exit_fill_price: float,
        exit_time_ms: Optional[int] = None,
    ) -> CryptoFillReconciliationRecord:
        """
        Executes Target 1 Staged Exit:
          - Closes 50% of position.
          - Calculates net P&L and fees.
          - Updates remaining_qty for runner.
        """
        now_ms = exit_time_ms or int(time.time() * 1000)
        rec = self._records.get(sig.signal_id)
        if not rec:
            rec = self.reconcile_entry(sig, float(sig.actual_fill_price or sig.trigger), sig.quantity or 0.01)

        close_qty = min(rec.t1_qty, rec.remaining_qty)
        is_long = sig.direction == "LONG"

        if is_long:
            gross_pnl = (exit_fill_price - rec.entry_fill_price) * close_qty
        else:
            gross_pnl = (rec.entry_fill_price - exit_fill_price) * close_qty

        notional_exit = round(exit_fill_price * close_qty, 2)
        fee_exit = round(notional_exit * TAKER_FEE_RATE, 4)
        slip_exit = round(notional_exit * SLIPPAGE_BPS_RATE, 4)
        net_pnl = round(gross_pnl - fee_exit - slip_exit, 4)

        rec.t1_fill_price = exit_fill_price
        rec.t1_gross_pnl_usd = round(gross_pnl, 2)
        rec.t1_net_pnl_usd = round(net_pnl, 2)
        rec.total_gross_pnl_usd = round(rec.total_gross_pnl_usd + gross_pnl, 2)
        rec.total_fees_usd = round(rec.total_fees_usd + fee_exit, 4)
        rec.total_slippage_usd = round(rec.total_slippage_usd + slip_exit, 4)
        rec.total_net_pnl_usd = round(rec.total_net_pnl_usd + net_pnl, 2)

        rec.remaining_qty = max(0.0, round(rec.remaining_qty - close_qty, 4))
        sig.remaining_qty = Decimal(str(rec.remaining_qty))
        sig.t1_realized_qty = Decimal(str(close_qty))

        rec.fills.append(
            CryptoStageFill(
                stage="TARGET_1",
                price=exit_fill_price,
                quantity=close_qty,
                timestamp_utc=now_ms,
                notional_usd=notional_exit,
                fee_usd=fee_exit,
                slippage_usd=slip_exit,
                gross_pnl_usd=round(gross_pnl, 2),
                net_pnl_usd=round(net_pnl, 2),
            )
        )
        rec.updated_at_utc = now_ms
        logger.info(
            "crypto_fill_reconciled_t1",
            signal_id=sig.signal_id,
            exit_price=exit_fill_price,
            closed_qty=close_qty,
            remaining_qty=rec.remaining_qty,
            net_pnl=net_pnl,
        )
        return rec

    def reconcile_final_exit(
        self,
        sig: CryptoSignalInstance,
        exit_fill_price: float,
        exit_reason: str,
        exit_time_ms: Optional[int] = None,
    ) -> CryptoFillReconciliationRecord:
        """
        Executes Final Exit for remaining runner:
          - Closes 100% of remaining_qty.
          - Calculates blended net P&L and net R-multiple.
          - Marks trade fully closed.
        """
        now_ms = exit_time_ms or int(time.time() * 1000)
        rec = self._records.get(sig.signal_id)
        if not rec:
            rec = self.reconcile_entry(sig, float(sig.actual_fill_price or sig.trigger), sig.quantity or 0.01)

        close_qty = rec.remaining_qty
        is_long = sig.direction == "LONG"

        if close_qty > 0:
            if is_long:
                gross_pnl = (exit_fill_price - rec.entry_fill_price) * close_qty
            else:
                gross_pnl = (rec.entry_fill_price - exit_fill_price) * close_qty

            notional_exit = round(exit_fill_price * close_qty, 2)
            fee_exit = round(notional_exit * TAKER_FEE_RATE, 4)
            slip_exit = round(notional_exit * SLIPPAGE_BPS_RATE, 4)
            net_pnl = round(gross_pnl - fee_exit - slip_exit, 4)

            rec.final_fill_price = exit_fill_price
            rec.final_gross_pnl_usd = round(gross_pnl, 2)
            rec.final_net_pnl_usd = round(net_pnl, 2)
            rec.total_gross_pnl_usd = round(rec.total_gross_pnl_usd + gross_pnl, 2)
            rec.total_fees_usd = round(rec.total_fees_usd + fee_exit, 4)
            rec.total_slippage_usd = round(rec.total_slippage_usd + slip_exit, 4)
            rec.total_net_pnl_usd = round(rec.total_net_pnl_usd + net_pnl, 2)

            rec.fills.append(
                CryptoStageFill(
                    stage=exit_reason,
                    price=exit_fill_price,
                    quantity=close_qty,
                    timestamp_utc=now_ms,
                    notional_usd=notional_exit,
                    fee_usd=fee_exit,
                    slippage_usd=slip_exit,
                    gross_pnl_usd=round(gross_pnl, 2),
                    net_pnl_usd=round(net_pnl, 2),
                )
            )

        rec.remaining_qty = 0.0
        sig.remaining_qty = Decimal("0")
        rec.is_fully_closed = True
        rec.exit_reason = exit_reason

        # Calculate True Blended R-Multiples
        # (no arbitrary floor: guard only against division by zero with a
        # 0.1%-of-notional fallback so R stays meaningful for tiny risk budgets)
        if rec.initial_risk_usd > 0:
            risk_ref = rec.initial_risk_usd
        else:
            risk_ref = max(1.0, abs(rec.entry_fill_price) * rec.initial_qty * 0.001)
        rec.realized_rr_gross = round(rec.total_gross_pnl_usd / risk_ref, 2)
        rec.realized_rr_net = round(rec.total_net_pnl_usd / risk_ref, 2)

        sig.exit_price = Decimal(str(exit_fill_price))
        sig.realized_rr_gross = rec.realized_rr_gross
        sig.realized_rr_net = rec.realized_rr_net
        sig.realized_rr = rec.realized_rr_net
        sig.fees_usd = rec.total_fees_usd
        sig.net_pnl_usd = rec.total_net_pnl_usd

        rec.updated_at_utc = now_ms
        logger.info(
            "crypto_fill_reconciled_final",
            signal_id=sig.signal_id,
            exit_reason=exit_reason,
            exit_price=exit_fill_price,
            net_pnl_usd=rec.total_net_pnl_usd,
            realized_rr_net=rec.realized_rr_net,
        )
        return rec

    def get_record(self, signal_id: str) -> Optional[CryptoFillReconciliationRecord]:
        return self._records.get(signal_id)


crypto_fill_reconciler = CryptoFillReconciler()
