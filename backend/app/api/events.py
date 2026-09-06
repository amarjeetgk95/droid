from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
import structlog

from app.event_engine.models import (
    CanonicalEvent,
    EventCreate,
    EventUpdate,
    EventScoreSnapshot,
    EventComparable,
    PredictionSnapshot,
)
from app.event_engine.service import event_engine_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/events", tags=["Event Intelligence Engine"])


# ============================================================
# 1. Static Query Endpoints (Must precede /{event_id})
# ============================================================

@router.get("/upcoming", response_model=list[CanonicalEvent])
async def get_upcoming_events(limit: int = Query(default=50, ge=1, le=100)):
    """Retrieve upcoming scheduled, approaching, or active market events."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    return event_engine_service.get_upcoming_events(limit=limit)


@router.get("/today", response_model=list[CanonicalEvent])
async def get_today_events():
    """Retrieve market events scheduled or occurring today (IST)."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    return event_engine_service.get_today_events()


@router.get("/alerts/queue")
async def get_alerts_queue():
    """Retrieve internal alert and review queue items (§29)."""
    from app.event_engine.alert_service import event_alert_service
    return event_alert_service.get_all_alerts()


@router.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, user: str = Query(default="OPS_DESK")):
    """Acknowledge an alert in the internal review queue."""
    from app.event_engine.alert_service import event_alert_service
    alert = event_alert_service.acknowledge_alert(alert_id, user_name=user)
    if not alert:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Alert '{alert_id}' not found")
    return alert


@router.get("/shadow-signals")
async def get_shadow_signals():
    """Retrieve forward-testing signals operating in SHADOW_MODE (§3, §27)."""
    from app.event_engine.signal_bridge import event_signal_bridge
    return event_signal_bridge.get_shadow_records()


@router.post("/rbi/sync", response_model=list[CanonicalEvent])
async def sync_rbi_events():
    """Trigger synchronization from official Reserve Bank of India source adapter."""
    events = await event_engine_service.sync_rbi_events()
    return events


@router.post("/corporate/sync", response_model=list[CanonicalEvent])
async def sync_corporate_events():
    """Trigger synchronization from official NSE and BSE corporate source adapters."""
    return await event_engine_service.sync_corporate_events()


@router.post("/manual", response_model=CanonicalEvent, status_code=status.HTTP_201_CREATED)
async def create_manual_event(payload: EventCreate):
    """Admin/Operations endpoint for manual event entry or official fallback (§5)."""
    return await event_engine_service.create_manual_event(payload)


@router.get("/analytics/track-record")
async def get_track_record():
    """Statistical Edge Validation & Track Record Summary (§23, §24)."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    return event_engine_service.get_track_record()


@router.get("/sources/health")
async def get_sources_health():
    """Source adapter health telemetry, latencies, and circuit breaker status (§5, §34)."""
    return event_engine_service.get_source_health()


@router.get("/risk/overlay")
async def get_risk_overlay(underlying: str = Query(default="BANKNIFTY")):
    """Event-aware risk overlay parameters and proximity dampeners (§28)."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    return event_engine_service.get_risk_overlay(underlying=underlying)


@router.post("/calibrate")
async def calibrate_events():
    """Trigger empirical market impact calibration across all canonical events (§14)."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    return event_engine_service.calibrate_all_events()


# ============================================================
# 2. Parameterized Endpoints (/{event_id}/...)
# ============================================================

@router.get("/{event_id}", response_model=CanonicalEvent)
async def get_event_detail(event_id: str):
    """Retrieve full canonical event details, score breakdown, and impact mappings."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    event = event_engine_service.get_event_by_id(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found",
        )
    return event


@router.get("/{event_id}/scores", response_model=EventScoreSnapshot)
async def get_event_scores(event_id: str):
    """Retrieve 3-dimension scores (Importance, Market Impact, Opportunity) and breakdown."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    event = event_engine_service.get_event_by_id(event_id)
    if not event or not event.scores:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scores for event '{event_id}' not found",
        )
    return event.scores


@router.get("/{event_id}/comparables", response_model=list[EventComparable])
async def get_event_comparables(event_id: str):
    """Retrieve historical comparables adhering to strict anti-lookahead cutoffs."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    event = event_engine_service.get_event_by_id(event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event '{event_id}' not found",
        )
    return event.comparables


@router.get("/{event_id}/prediction", response_model=PredictionSnapshot)
async def get_event_prediction(event_id: str):
    """Retrieve immutable prediction snapshot with data cutoff timestamps."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    event = event_engine_service.get_event_by_id(event_id)
    if not event or not event.latest_prediction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Prediction snapshot for event '{event_id}' not found",
        )
    return event.latest_prediction


@router.get("/{event_id}/live-opportunity")
async def get_live_opportunity(event_id: str):
    """Evaluate real-time Trading Opportunity Score & live options context (§15, §16, §18)."""
    if not event_engine_service._initialized:
        await event_engine_service.initialize()
    try:
        return await event_engine_service.get_live_opportunity(event_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{event_id}/outcome")
async def get_event_outcome(event_id: str):
    """Retrieve post-event measured reaction and realized outcome (§24)."""
    from app.event_engine.outcome_recorder import event_outcome_recorder
    outcome = event_outcome_recorder.get_outcome(event_id)
    if not outcome:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Outcome for event '{event_id}' has not yet been settled",
        )
    return outcome
