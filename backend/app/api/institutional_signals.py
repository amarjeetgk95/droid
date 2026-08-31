from fastapi import APIRouter, Query
from typing import Literal

from app.institutional.signal_center import signal_center

router_signals = APIRouter(prefix="/api/v1/institutional", tags=["institutional-signals"])

@router_signals.get("/signals/active")
async def get_active_signals(
    instrument: str | None = Query(None, description="Filter by NIFTY/BANKNIFTY/SENSEX/BTCUSD"),
    status: str | None = Query(None, description="Filter by CONFIRMED/WATCH/POSSIBLE_BREAKOUT etc"),
):
    data = await signal_center.active_setups(instrument=instrument, status=status)
    return {"signals": data, "count": len(data), "generated_at_ms": __import__("time").time()*1000}

@router_signals.get("/signals/history")
async def get_signals_history(limit: int = 20):
    from app.institutional.audit import audit_trail
    return {"records": audit_trail.recent(limit)}
