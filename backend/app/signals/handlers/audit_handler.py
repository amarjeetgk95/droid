"""
Audit Event Handler for Droid Signal Engine (Version 6.0)

Subscribes to SignalEventBus events and synchronizes FSM state transitions to the
SignalAuditLedger and trade records.
"""
from __future__ import annotations

from typing import Any
import structlog

from app.signals.event_bus import SignalEvent

logger = structlog.get_logger()


async def handle_signal_transitioned_audit(event: SignalEvent) -> None:
    """Syncs state transition to audit ledger."""
    try:
        from app.signals.audit_ledger import signal_audit_ledger

        payload = event.payload
        to_state = payload.get("to_state")
        if not to_state:
            return

        market_price = payload.get("market_price")
        reason = payload.get("reason", "")

        signal_audit_ledger.record_state_transition(
            signal_id=event.signal_id,
            to_state=to_state,
            market_price=float(market_price) if market_price is not None else None,
            reason=reason,
        )
    except Exception as e:
        logger.warning("audit_handler_transition_err", signal_id=event.signal_id, error=str(e)[:200])
