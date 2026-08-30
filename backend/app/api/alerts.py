from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_current_user, AuthUser
from app.core.database import get_db_session
from app.services.alert_service import alert_service
from app.models.alert import AlertPayload
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="alert_and_telemetry_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


def _parse_user_uuid(user: Optional[AuthUser]) -> Optional[UUID]:
    if not user or not user.user_id:
        return None
    try:
        return UUID(user.user_id)
    except Exception:
        return None


@router.get("")
async def list_alert_rules(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Retrieve all configured alert rules."""
    try:
        user_uuid = _parse_user_uuid(user)
        rules = await alert_service.get_rules_async(session, user_uuid)
        return {
            "data": [r.model_dump(mode="json") for r in rules],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_alert_rule(
    payload: AlertPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Create a new alert rule."""
    try:
        user_uuid = _parse_user_uuid(user)
        rule = await alert_service.create_rule_async(payload, session, user_uuid)
        return {
            "data": rule.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{alert_id}")
async def delete_alert_rule(
    alert_id: str,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Delete an alert rule."""
    try:
        user_uuid = _parse_user_uuid(user)
        success = await alert_service.delete_rule_async(alert_id, session, user_uuid)
        if not success:
            raise HTTPException(status_code=404, detail="Alert rule not found")
        return {
            "data": {"alert_id": alert_id, "deleted": True},
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{alert_id}/toggle")
async def toggle_alert_rule(
    alert_id: str,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Toggle active/disabled state of an alert rule."""
    try:
        user_uuid = _parse_user_uuid(user)
        rule = await alert_service.toggle_rule_async(alert_id, session, user_uuid)
        return {
            "data": rule.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/evaluate")
async def evaluate_alert_rules():
    """Trigger real-time evaluation of all active alert rules."""
    try:
        triggered = await alert_service.evaluate_rules()
        return {
            "data": [t.model_dump(mode="json") for t in triggered],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_alert_history(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Retrieve historical triggered alert notifications."""
    try:
        user_uuid = _parse_user_uuid(user)
        history = await alert_service.get_history_async(session, user_uuid)
        return {
            "data": [h.model_dump(mode="json") for h in history],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/telemetry")
async def get_system_telemetry():
    """Retrieve production system telemetry, memory usage, and worker states."""
    try:
        telemetry = alert_service.get_telemetry()
        return {
            "data": telemetry.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
