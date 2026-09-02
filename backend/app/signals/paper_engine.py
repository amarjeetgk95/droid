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

from app.signals.contract_resolver import calculate_position_sizing, normalize_price, validate_underlying
from app.signals.fsm import signal_fsm, SignalInstance
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

        # Position Sizing
        avail_cap = capital_override or getattr(paper_service, "_initial_capital", 1000000.0)
        
        if lots_override and lots_override > 0:
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
        spread_impact = raw_price * 0.0005
        fill_price = round(raw_price + spread_impact, 2) if side == "BUY" else round(raw_price - spread_impact, 2)

        # Place order into Paper Trading Service
        order_payload = OrderPayload(
            symbol=broker_sym,
            underlying=u,
            side=side,
            order_type="MARKET",
            product="INTRADAY",
            quantity=final_qty,
            price=fill_price,
        )
        paper_order = await paper_service.place_order(order_payload)

        # Update FSM with order details
        sig.paper_order = paper_order.model_dump()
        if sig.fsm_state in ("DETECTED", "VALIDATED", "ARMED"):
            signal_fsm.transition(sig.signal_id, "CONFIRMED", market_price=Decimal(str(fill_price)), reason="PAPER_TRADE_EXECUTED")

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


signal_paper_engine = SignalPaperEngine()
