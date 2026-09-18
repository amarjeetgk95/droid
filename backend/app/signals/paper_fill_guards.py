"""Off-domain fill remedies for the signal paper engine.

Extracted verbatim from :mod:`app.signals.paper_engine`
(``SignalPaperEngine._rollback_off_domain_fill``). The engine binds this
function back onto the class as a staticmethod, preserving the original
call and patch surface.
"""
from __future__ import annotations

from typing import Optional

import structlog

from app.services.paper_service import paper_service

logger = structlog.get_logger()


async def rollback_off_domain_fill(
    broker_symbol: str,
    product: str,
    quantity: int,
    signal_id: str,
) -> Optional[float]:
    """Unwind a service-side position booked for an off-domain fill.

    Squares the position off at the service's live (same mispriced source)
    quote so the round trip nets to ~friction cost instead of realizing a
    fabricated P&L against the mismatched fill. Returns the round-trip
    realized PnL when the rollback filled, else None. Best-effort: never
    raises into the rejection path, but a failed rollback is logged so the
    open position is never silent.
    """
    pos_id = f"{broker_symbol}_{product}"
    try:
        snapshot = await paper_service.get_position_snapshot(pos_id)
        if snapshot is None or not snapshot.is_open:
            return None
        await paper_service.square_off_position(pos_id, allow_closed_market=True)
        closed = await paper_service.get_position_snapshot(pos_id)
        realized = round(float(getattr(closed, "realized_pnl", 0.0) or 0.0), 2)
        logger.warning(
            "paper_fill_rollback_executed",
            signal_id=signal_id,
            reason="OFF_DOMAIN_FILL",
            broker_symbol=broker_symbol,
            quantity=quantity,
            realized_pnl_round_trip=realized,
        )
        return realized
    except Exception as rb_err:
        logger.error(
            "paper_fill_rollback_failed",
            signal_id=signal_id,
            reason="OFF_DOMAIN_FILL",
            broker_symbol=broker_symbol,
            error=str(rb_err)[:200],
        )
        return None
