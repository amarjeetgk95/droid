from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.envelope import envelope
from app.core.database import get_db_session
from app.core.security import AuthUser, get_current_user
from app.models.market import DataStatus
from app.models.paper import BasketOrderPayload, OrderPayload
from app.services.paper_service import paper_service

router = APIRouter(prefix="/api/v1/paper", tags=["paper"])

_PROVIDER = "paper_trading_engine"


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
    user_uuid = _parse_user_uuid(user)
    summary = await paper_service.get_portfolio_summary(session, user_uuid)
    return envelope(summary, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/positions")
async def get_positions(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Retrieve active and closed virtual trading positions."""
    user_uuid = _parse_user_uuid(user)
    positions = await paper_service.get_positions(session, user_uuid)
    return envelope(positions, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.get("/orders")
async def get_orders(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Retrieve virtual order book execution logs (paginated).

    Query params: ``limit`` (1-500), ``offset``, ``status`` (PENDING/FILLED/...).
    """
    user_uuid = _parse_user_uuid(user)
    orders = await paper_service.get_orders_async(session, user_uuid, limit=limit, offset=offset)
    if status:
        s = status.upper()
        orders = [o for o in orders if o.status == s]
    return envelope(orders, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/order")
async def place_virtual_order(
    payload: OrderPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Place and execute a single virtual order."""
    user_uuid = _parse_user_uuid(user)
    order = await paper_service.place_order(payload, session, user_uuid)
    return envelope(order, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/basket")
async def place_strategy_basket(
    payload: BasketOrderPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Execute a multi-leg strategy basket."""
    user_uuid = _parse_user_uuid(user)
    orders = await paper_service.place_basket(payload, session, user_uuid)
    return envelope(orders, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/position/square-off/{position_id}")
async def square_off_single_position(
    position_id: str,
    allow_closed_market: bool = False,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Close an open position at current market price."""
    user_uuid = _parse_user_uuid(user)
    try:
        closed = await paper_service.square_off_position(
            position_id, session, user_uuid, allow_closed_market=allow_closed_market
        )
    except ValueError as ve:
        msg = str(ve)
        raise HTTPException(status_code=404 if "not found" in msg.lower() else 400, detail=msg)
    return envelope(closed, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/order/{order_id}/cancel")
async def cancel_pending_order(
    order_id: str,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Cancel a resting PENDING (LIMIT/SL) order."""
    user_uuid = _parse_user_uuid(user)
    try:
        cancelled = await paper_service.cancel_order(order_id, session, user_uuid)
    except ValueError as ve:
        msg = str(ve)
        raise HTTPException(status_code=404 if "not found" in msg.lower() else 400, detail=msg)
    return envelope(cancelled, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/square-off-all")
async def square_off_all_positions(
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Emergency square off of all active positions."""
    user_uuid = _parse_user_uuid(user)
    closed = await paper_service.square_off_all(session, user_uuid)
    return envelope(closed, provider=_PROVIDER, status=DataStatus.OFFLINE)


class SetCapitalPayload(BaseModel):
    capital: float


class MarginPreviewPayload(BaseModel):
    symbol: str
    underlying: str
    side: str = "BUY"
    quantity: int = 1
    price: float = 0.0


@router.post("/preview")
async def preview_margin(
    payload: MarginPreviewPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Estimate margin + premium for a hypothetical order without executing it."""
    from app.quant.margin import calculate_required_margin

    sym = (payload.symbol or "").upper()
    is_opt = "CE" in sym or "PE" in sym
    if is_opt:
        inst_type = "OPTION_BUY" if payload.side.upper() == "BUY" else "OPTION_SELL"
    else:
        inst_type = "FUTURES"
    req_margin = calculate_required_margin(
        instrument_type=inst_type,  # type: ignore[arg-type]
        underlying=payload.underlying,
        price=payload.price,
        quantity=payload.quantity,
        is_hedged=False,
    )
    user_uuid = _parse_user_uuid(user)
    portfolio = await paper_service.get_portfolio_summary(session, user_uuid)
    premium = round(payload.price * payload.quantity, 2) if is_opt and payload.side.upper() == "BUY" else 0.0
    return envelope(
        {
            "required_margin": req_margin,
            "premium": premium,
            "available_margin": portfolio.available_margin,
            "affordable": req_margin <= portfolio.available_margin,
        },
        provider=_PROVIDER,
        status=DataStatus.OFFLINE,
    )


@router.post("/wallet")
async def set_paper_wallet_capital(
    payload: SetCapitalPayload,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Set custom virtual capital for the paper trading wallet."""
    user_uuid = _parse_user_uuid(user)
    try:
        summary = await paper_service.set_initial_capital_async(payload.capital, session, user_uuid)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    return envelope(summary, provider=_PROVIDER, status=DataStatus.OFFLINE)


@router.post("/reset")
async def reset_paper_trading_account(
    payload: Optional[SetCapitalPayload] = None,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Reset virtual account to baseline or custom capital."""
    user_uuid = _parse_user_uuid(user)
    cap = payload.capital if payload else None
    summary = await paper_service.reset_portfolio_async(session, user_uuid, capital=cap)
    return envelope(summary, provider=_PROVIDER, status=DataStatus.OFFLINE)
