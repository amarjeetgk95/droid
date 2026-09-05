"""
Lot-Aware Realistic Paper Execution Adapter for Signal Centre
Models:
  - Dynamic lot sizing from InstrumentMaster
  - Bid-Ask spread impact & ATR slippage
  - Integration with app.services.paper_service
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
import structlog
from pydantic import BaseModel

from app.signals.contract_resolver import calculate_position_sizing, validate_underlying
from app.signals.fsm import signal_fsm
from app.services.paper_service import paper_service
from app.models.paper import OrderPayload

logger = structlog.get_logger()


class SignalPaperExecutionResult(BaseModel):
    success: bool
    signal_id: str
    underlying: str
    strategy: str
    side: str
    quantity: int
    lots: int
    fill_price: float
    stop_loss: float
    target_1: float
    target_2: float
    order_id: str
    status: str
    message: str


class SignalPaperEngine:
    """
    Executes validated & confirmed signals in the paper trading portfolio.
    """

    async def execute_signal(
        self,
        signal_id: str,
        capital_override: Optional[float] = None,
        risk_percent: float = 2.0,
        lots_override: Optional[int] = None,
        quantity_override: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> SignalPaperExecutionResult:
        sig = signal_fsm.get(signal_id)
        if not sig:
            raise ValueError("Signal not found")

        u = validate_underlying(sig.underlying)
        opt = sig.option_contract or {}
        lot_size = int(opt.get("lot_size", 75 if u == "NIFTY" else (30 if u == "BANKNIFTY" else 10)))
        broker_sym = opt.get("broker_symbol", f"{u}_OPT")

        # Determine side
        side = "BUY"
        direction_label = "CE" if "CALL" in sig.direction else "PE"

        # ── Centralized Market Session Check ──
        from app.services.calendar_service import calendar_service
        perm = calendar_service.can_trade_now()
        if not allow_closed_market and not perm.allowed:
            logger.warning("paper_execution_blocked_market_closed", signal_id=signal_id, reason=perm.reason)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=0,
                lots=0,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message=f"MARKET_CLOSED: {perm.reason} (NSE trading hours: 09:15 - 15:30 IST)",
            )

        # Position Sizing
        avail_cap = capital_override or getattr(paper_service, "_initial_capital", 1000000.0)
        
        if quantity_override and quantity_override > 0:
            final_qty = quantity_override
            final_lots = max(1, quantity_override // lot_size)
        elif lots_override and lots_override > 0:
            final_lots = lots_override
            final_qty = final_lots * lot_size
        else:
            sizing = calculate_position_sizing(
                available_capital=avail_cap,
                risk_percent=risk_percent,
                entry_price=sig.spot_price,
                stop_loss=sig.stop_loss,
                lot_size=lot_size,
            )
            final_lots = max(1, sizing["lots"])
            final_qty = final_lots * lot_size

        # Estimate Fill Price with simulated spread (0.05%) and slippage
        raw_price = float(sig.spot_price)
        if raw_price <= 0:
            logger.warning("paper_execution_blocked_invalid_spot_price", signal_id=signal_id, spot=raw_price)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=0,
                lots=0,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message="INVALID_PRICE: Spot price is non-positive",
            )

        # If signal represents an option contract, estimate option premium instead of spot price
        from app.signals.fill_reconciler import option_fill_reconciler
        if sig.option_contract:
            strike = float(sig.option_contract.get("strike", raw_price))
            opt_type = str(sig.option_contract.get("option_type", "CE"))
            dte = float(sig.option_contract.get("dte", 3.0))
            base_price = option_fill_reconciler.estimate_option_premium(
                spot=raw_price,
                strike=strike,
                option_type=opt_type,
                dte_days=dte,
            )
        else:
            base_price = raw_price

        spread_impact = base_price * 0.0005
        fill_price = round(base_price + spread_impact, 2) if side == "BUY" else round(base_price - spread_impact, 2)
        if fill_price <= 0:
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=0,
                lots=0,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id="",
                status="REJECTED",
                message="INVALID_PRICE: Fill price is non-positive",
            )

        # Place order into Paper Trading Service (final hard safety boundary)
        order_payload = OrderPayload(
            symbol=broker_sym,
            underlying=u,
            side=side,
            order_type="MARKET",
            product="INTRADAY",
            quantity=final_qty,
            price=fill_price,
        )
        paper_order = await paper_service.place_order(order_payload, allow_closed_market=allow_closed_market)

        if paper_order.status == "REJECTED":
            logger.warning("paper_order_rejected_by_service", signal_id=signal_id, reason=paper_order.rejection_reason)
            return SignalPaperExecutionResult(
                success=False,
                signal_id=signal_id,
                underlying=u,
                strategy=sig.strategy,
                side=f"BUY_{direction_label}",
                quantity=final_qty,
                lots=final_lots,
                fill_price=0.0,
                stop_loss=float(sig.stop_loss),
                target_1=float(sig.target_1),
                target_2=float(sig.target_2),
                order_id=paper_order.order_id,
                status="REJECTED",
                message=paper_order.rejection_reason or "Order rejected by paper service",
            )

        # Update FSM with order details
        sig.paper_order = paper_order.model_dump()
        if sig.fsm_state in ("DETECTED", "VALIDATED", "ARMED"):
            signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=Decimal(str(fill_price)), reason="PAPER_TRADE_EXECUTED")

        # Record into Signal Audit Ledger
        try:
            from app.signals.audit_ledger import signal_audit_ledger
            # Ensure trade is registered in ledger first
            if not signal_audit_ledger.get(signal_id):
                signal_audit_ledger.record_signal_created(
                    signal_id=sig.signal_id,
                    underlying=sig.underlying,
                    strategy=sig.strategy,
                    direction=sig.direction,
                    timeframe=sig.timeframe,
                    spot_price=float(sig.spot_price),
                    trigger=float(sig.trigger),
                    stop_loss=float(sig.stop_loss),
                    target_1=float(sig.target_1),
                    target_2=float(sig.target_2),
                    confidence=float(sig.confidence),
                    option_contract=sig.option_contract,
                    lots=final_lots,
                    status="CONFIRMED",
                )
            signal_audit_ledger.record_paper_executed(
                signal_id=signal_id,
                paper_order_id=paper_order.order_id,
                fill_price=fill_price,
                quantity=final_qty,
                lots=final_lots,
                side=side,
                margin_used=fill_price * final_qty,
            )
        except Exception as ae:
            logger.warning("audit_record_paper_failed", error=str(ae))

        logger.info("signal_paper_executed", signal_id=signal_id, order_id=paper_order.order_id, lots=final_lots, qty=final_qty)

        return SignalPaperExecutionResult(
            success=True,
            signal_id=signal_id,
            underlying=u,
            strategy=sig.strategy,
            side=f"BUY_{direction_label}",
            quantity=final_qty,
            lots=final_lots,
            fill_price=fill_price,
            stop_loss=float(sig.stop_loss),
            target_1=float(sig.target_1),
            target_2=float(sig.target_2),
            order_id=paper_order.order_id,
            status=paper_order.status,
            message=f"Filled {final_lots} Lots ({final_qty} Qty) {broker_sym} @ ₹{fill_price:,.2f}",
        )

    async def close_signal_position(
        self,
        signal_id: str,
        exit_price: float,
        reason: str = "TARGET_HIT",
        quantity_to_close: Optional[int] = None,
        allow_closed_market: bool = False,
    ) -> Optional[Any]:
        """
        Closes full or partial open paper position for a signal and records the actual profit and loss audit.
        """
        sig = signal_fsm.get(signal_id)
        if not sig or not sig.paper_order:
            return None

        from app.signals.audit_ledger import signal_audit_ledger

        broker_sym = sig.paper_order.get("symbol")
        qty = sig.paper_order.get("quantity")
        if not broker_sym or not qty:
            return None

        # Allow closed market execution for square-off / cleanup reasons
        permit_closed = allow_closed_market or reason in (
            "MARKET_CLOSED", "EOD_SQUAREOFF", "DELETED_BY_USER", "TIME_STOP_EXCEEDED", "RUNNER_TTL_EXCEEDED"
        )

        pos_id = f"{broker_sym}_INTRADAY"
        if pos_id in paper_service._positions and paper_service._positions[pos_id].is_open:
            pos = paper_service._positions[pos_id]
            exit_side = "SELL" if pos.side == "BUY" else "BUY"
            final_close_qty = quantity_to_close if (quantity_to_close and quantity_to_close <= pos.quantity) else pos.quantity
            exit_payload = OrderPayload(
                symbol=pos.symbol,
                underlying=pos.underlying,
                side=exit_side,
                order_type="MARKET",
                product=pos.product,
                quantity=final_close_qty,
                price=exit_price,
            )
            await paper_service.place_order(exit_payload, allow_closed_market=permit_closed)
            logger.info("paper_position_closed", signal_id=signal_id, symbol=broker_sym, exit_price=exit_price, qty=final_close_qty, reason=reason)

        rec = signal_audit_ledger.record_square_off(
            signal_id=signal_id,
            exit_price=exit_price,
            exit_reason=reason,
        )
        return rec


signal_paper_engine = SignalPaperEngine()

