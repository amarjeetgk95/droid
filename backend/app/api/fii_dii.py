from datetime import datetime, timezone
from fastapi import APIRouter
from app.api.envelope import envelope
from app.models.market import DataStatus
from app.services.fii_dii_service import fii_dii_service

router = APIRouter(prefix="/api/v1/fii-dii", tags=["fii-dii"])

_PROVIDER = "institutional_derivatives_tracker"


@router.get("/overview")
async def get_fii_dii_overview():
    """Retrieve institutional FII/DII net derivatives positioning and cash turnover."""
    overview = fii_dii_service.get_institutional_overview()
    return envelope(overview, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/flow")
async def get_flow_snapshot():
    """PIT-safe flow snapshot (T+1 available) + composite + drift flag.

    Frontend v2 minimal: probability context (flow z, composite 0-100,
    settleability note). `live:false` always — daily file, never intraday.
    """
    from app.institutional.flow_store import flow_store
    from app.institutional.composite import compute_composite
    from app.institutional.drift import FLAG as _drift_flag

    now = datetime.now(timezone.utc)
    snap = flow_store.as_of(now)
    comp = compute_composite(snap, None, None, None, None, "UNKNOWN") if snap else None
    drift = None
    try:
        import json as _json

        if _drift_flag.exists():
            drift = _json.loads(_drift_flag.read_text(encoding="utf-8"))
    except Exception:
        drift = None
    payload = {
        "timestamp": now.isoformat(),
        "live": False,
        "pit_note": "daily file, available_time=T+1 18:00 IST; intraday use of today's flow is lookahead",
        "flow": {
            "event_date": getattr(snap, "event_date", None),
            "available_time_utc": getattr(snap, "available_time_utc", None),
            "fii_cash_net_crores": getattr(snap, "fii_cash_net_crores", None),
            "dii_cash_net_crores": getattr(snap, "dii_cash_net_crores", None),
            "fii_cash_5d_z": getattr(snap, "fii_cash_5d_z", None),
            "dii_cash_5d_z": getattr(snap, "dii_cash_5d_z", None),
            "fii_fut_net": getattr(snap, "fii_fut_net", None),
            "fii_lsr": getattr(snap, "fii_lsr", None),
            "n_days_window": getattr(snap, "n_days_window", 0),
        } if snap else None,
        "composite": comp,
        "drift": drift,
        "futures": {"status": "UNAVAILABLE", "note": "no live futures feed; basis/OI not synthesized"},
    }
    return envelope(payload, provider="institutional_flow_store", status=DataStatus.OFFLINE)
