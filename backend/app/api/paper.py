from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.security import get_current_user, AuthUser
from app.core.database import get_db_session
from app.services.paper_service import paper_service
from app.models.paper import OrderPayload, BasketOrderPayload
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/paper", tags=["paper"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="paper_trading_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.OFFLINE,
    )


def _parse_user_uuid(user: Optional[AuthUser]) -> Optional[UUID]:
    if not user or not user.user_id:
        return None
    try:
        return UUID(user.user_id)
    except Exception:
        return None


@router.get("/portfolio")
async def get_portfolio_summary(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Retrieve virtual portfolio balance, MTM, and margin usage."""
    try:
        user_uuid = _parse_user_uuid(user)
        summary = await paper_service.get_portfolio_summary(session, user_uuid)
        return {
            "data": summary.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/positions")
async def get_positions(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Retrieve active and closed virtual trading positions."""
    try:
        user_uuid = _parse_user_uuid(user)
        positions = await paper_service.get_positions(session, user_uuid)
        return {
            "data": [p.model_dump(mode="json") for p in positions],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/orders")
async def get_orders(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Retrieve virtual order book execution logs."""
    try:
        user_uuid = _parse_user_uuid(user)
        orders = await paper_service.get_orders_async(session, user_uuid)
        return {
            "data": [o.model_dump(mode="json") for o in orders],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/order")
async def place_virtual_order(
    payload: OrderPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Place and execute a single virtual order."""
    try:
        user_uuid = _parse_user_uuid(user)
        order = await paper_service.place_order(payload, session, user_uuid)
        return {
            "data": order.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/basket")
async def place_strategy_basket(
    payload: BasketOrderPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Execute a multi-leg strategy basket."""
    try:
        user_uuid = _parse_user_uuid(user)
        orders = await paper_service.place_basket(payload, session, user_uuid)
        return {
            "data": [o.model_dump(mode="json") for o in orders],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/position/square-off/{position_id}")
async def square_off_single_position(
    position_id: str,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Close an open position at current market price."""
    try:
        user_uuid = _parse_user_uuid(user)
        closed = await paper_service.square_off_position(position_id, session, user_uuid)
        return {
            "data": closed.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/square-off-all")
async def square_off_all_positions(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Emergency square off of all active positions."""
    try:
        user_uuid = _parse_user_uuid(user)
        closed = await paper_service.square_off_all(session, user_uuid)
        return {
            "data": [c.model_dump(mode="json") for c in closed],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SetCapitalPayload(BaseModel):
    capital: float


@router.post("/wallet")
async def set_paper_wallet_capital(
    payload: SetCapitalPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Set custom virtual capital for the paper trading wallet."""
    try:
        user_uuid = _parse_user_uuid(user)
        summary = await paper_service.set_initial_capital_async(payload.capital, session, user_uuid)
        return {
            "data": summary.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset")
async def reset_paper_trading_account(
    payload: Optional[SetCapitalPayload] = None,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Reset virtual account to baseline or custom capital."""
    try:
        user_uuid = _parse_user_uuid(user)
        cap = payload.capital if payload else None
        summary = await paper_service.reset_portfolio_async(session, user_uuid, capital=cap)
        return {
            "data": summary.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
