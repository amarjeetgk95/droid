"""Duplicate-execution replay for the signal paper engine.

Extracted verbatim from :mod:`app.signals.paper_engine`
(``SignalPaperEngine._replay_filled_intent``) so the engine module stays
inside the LOC ratchet. The engine binds this function back onto the class
as a staticmethod, preserving the original call and patch surface.
"""
from __future__ import annotations

from typing import Any, Optional

from app.services.paper_service import paper_service
from app.signals.paper_results import SignalPaperExecutionResult


def replay_filled_intent(
    existing_intent: Any,
    sig: Any,
    underlying: str,
    direction_label: str,
    lot_size: int,
) -> Optional[SignalPaperExecutionResult]:
    """Rebuild the original success result for an already-FILLED intent.

    Source preference: the paper service order (live state), then the
    persisted intent ledger record, then the signal's own ``paper_order`` /
    registered Position. Returns None when no filled state can be proven,
    in which case the caller keeps the historical duplicate rejection.
    """
    fill_price = 0.0
    quantity = 0
    order_id = ""
    # The engine's success results label every fill CHAIN (the mark that
    # priced it); replay must return the same provenance as the original.
    fill_source = "CHAIN"
    chain_mark = None

    # 1. Paper service: the authoritative order record for this client id.
    try:
        client_id = str(existing_intent.broker_client_order_id or "")
        broker_id = str(existing_intent.broker_order_id or "")
        for order in paper_service.get_orders():
            if str(getattr(order, "status", "")) != "FILLED":
                continue
            matched = client_id and str(getattr(order, "client_order_id", "") or "") == client_id
            matched = matched or (broker_id and str(getattr(order, "order_id", "") or "") == broker_id)
            if matched:
                fill_price = float(order.fill_price or 0.0)
                quantity = int(order.quantity or 0)
                order_id = str(order.order_id or "")
                break
    except Exception:
        pass

    # 2. The persisted intent record (survives a service restart).
    if fill_price <= 0:
        try:
            fill_price = float(existing_intent.actual_fill_price or 0.0)
        except Exception:
            fill_price = 0.0
    if quantity <= 0:
        try:
            quantity = int(existing_intent.filled_quantity or 0)
        except Exception:
            quantity = 0
    if not order_id:
        order_id = str(existing_intent.broker_order_id or "")

    # 3. FSM paper_order / registered Position.
    po = sig.paper_order if isinstance(getattr(sig, "paper_order", None), dict) else None
    if po:
        if fill_price <= 0:
            try:
                fill_price = float(po.get("fill_price") or 0.0)
            except Exception:
                fill_price = 0.0
        if quantity <= 0:
            try:
                quantity = int(po.get("quantity") or 0)
            except Exception:
                quantity = 0
        if not order_id:
            order_id = str(po.get("order_id") or "")
        if chain_mark is None:
            try:
                _cm = po.get("chain_mark_at_fill")
                chain_mark = float(_cm) if _cm is not None else None
            except Exception:
                chain_mark = None
    if fill_price <= 0 or quantity <= 0 or not order_id:
        try:
            from app.signals.position import position_registry

            pos = position_registry.get_by_signal(sig.signal_id)
            if pos is not None:
                if fill_price <= 0:
                    fill_price = float(pos.entry_price or 0.0)
                if quantity <= 0:
                    quantity = int(pos.entry_quantity or 0)
                if not order_id:
                    order_id = str(pos.broker_order_id or "")
        except Exception:
            pass

    if fill_price <= 0 or quantity <= 0 or not order_id:
        return None

    lots = quantity // lot_size if lot_size > 0 else 0
    if lots < 1:
        lots = max(1, int(getattr(sig, "lots", 0) or 0))
    return SignalPaperExecutionResult(
        success=True,
        signal_id=sig.signal_id,
        underlying=underlying,
        strategy=sig.strategy,
        side=f"BUY_{direction_label}",
        quantity=quantity,
        lots=lots,
        fill_price=fill_price,
        stop_loss=float(sig.stop_loss),
        target_1=float(sig.target_1),
        target_2=float(sig.target_2),
        order_id=order_id,
        status="FILLED",
        message=(
            f"DUPLICATE_REPLAY: intent {existing_intent.execution_intent_id} already filled "
            f"as {order_id} ({lots} Lots / {quantity} Qty @ ₹{fill_price:,.2f})"
        ),
        fill_source=fill_source or "CHAIN",
        chain_mark_at_fill=chain_mark,
    )
