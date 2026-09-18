"""Paper-execution result model and price-domain vocabulary.

Extracted verbatim from :mod:`app.signals.paper_engine` so the execution
helpers (fill rollback, duplicate replay, exit failures) can build results
without importing the engine module, which would be circular.
``paper_engine`` re-exports every name here, so its public surface and all
existing ``from app.signals.paper_engine import ...`` callers are unchanged.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel

#: Price-domain OFF_DOMAIN: option premiums live <5000; index spot >5000.
#: A premium leg filled at spot scale (or vice versa) is the wrong instrument.
#: Same-domain fills must sit inside a 3% band of the chain mark.
OFF_DOMAIN_SPOT_THRESHOLD = 5000.0
OFF_DOMAIN_BAND_PCT = 0.03
#: Legacy alias (kept for compat; tightened from 10% to 3% band).
MAX_FILL_DEVIATION_FROM_CHAIN_MARK = 0.03

#: Intent TTL for PENDING orders (ms): stale PENDING auto-expires.
PENDING_INTENT_TTL_MS = 30_000


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
    # P1 provenance: where the fill came from + chain mark at fill time.
    fill_source: str = "CHAIN"
    chain_mark_at_fill: float | None = None


def exit_not_filled_result(sig: Any, order: Any) -> SignalPaperExecutionResult:
    """Explicit failure for a close whose exit order did not fill.

    Preserves the service's own status/rejection vocabulary so callers can
    surface the exact boundary rejection while the virtual position, the
    audit record and the signal FSM remain exactly as they were.
    """
    qty = int(getattr(order, "quantity", 0) or 0)
    lots = int(getattr(sig, "lots", 0) or 0)
    if lots <= 0:
        lot_size = int((sig.option_contract or {}).get("lot_size", 0) or 0)
        lots = max(1, qty // lot_size) if lot_size > 0 else 0
    status = str(getattr(order, "status", "REJECTED") or "REJECTED")
    return SignalPaperExecutionResult(
        success=False,
        signal_id=sig.signal_id,
        underlying=sig.underlying,
        strategy=sig.strategy,
        side=str(getattr(order, "side", "SELL") or "SELL"),
        quantity=qty,
        lots=lots,
        fill_price=0.0,
        stop_loss=float(sig.stop_loss),
        target_1=float(sig.target_1),
        target_2=float(sig.target_2),
        order_id=str(getattr(order, "order_id", "") or ""),
        status=status,
        message=getattr(order, "rejection_reason", None) or f"EXIT_NOT_FILLED: {status}",
        fill_source="NONE",
        chain_mark_at_fill=None,
    )
