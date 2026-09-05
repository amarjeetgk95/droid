"""
Centralized Market Session Guard for Signal Engine & Trading Operations.

Enforces strict exchange calendar checks (NSE trading hours: 09:15 - 15:30 IST,
weekends, official holidays, and special trading sessions).
"""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, TypeVar
from fastapi import HTTPException
import structlog

from app.services.calendar_service import calendar_service, MarketSessionPermission

logger = structlog.get_logger()

F = TypeVar("F", bound=Callable[..., Any])


class MarketClosedError(RuntimeError):
    """Raised when an operation requires an open market session but the market is closed."""

    def __init__(self, message: str, reason: str = "MARKET_CLOSED", session: str = "CLOSED"):
        super().__init__(message)
        self.reason = reason
        self.session = session


def require_market_open(allow_closed: bool = False) -> MarketSessionPermission:
    """
    Evaluates current market session permission.

    Raises:
        MarketClosedError: if market is closed and allow_closed is False.

    Returns:
        MarketSessionPermission: if market is open or allow_closed is True.
    """
    perm = calendar_service.can_trade_now()
    if not perm.allowed and not allow_closed:
        msg = f"Market is closed ({perm.reason}). NSE trading hours: 09:15 - 15:30 IST."
        logger.warning("market_session_guard_blocked", reason=perm.reason, session=perm.session)
        raise MarketClosedError(msg, reason=perm.reason, session=perm.session)
    return perm


def ensure_market_open_or_raise_http(allow_closed: bool = False, detail_prefix: str = "Signal generation blocked") -> MarketSessionPermission:
    """
    Evaluates market session and raises FastAPI HTTPException(400) if closed.
    """
    perm = calendar_service.can_trade_now()
    if not perm.allowed and not allow_closed:
        msg = f"{detail_prefix}: market is closed ({perm.reason}). NSE trading hours: 09:15 - 15:30 IST."
        logger.warning("http_market_session_guard_blocked", reason=perm.reason, session=perm.session)
        raise HTTPException(status_code=400, detail=msg)
    return perm


def market_hours_required(allow_closed_kwarg: str | None = None):
    """
    Decorator for async FastAPI route handlers or functions.
    Checks market hours before executing the wrapped function.
    """
    def decorator(func: F) -> F:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            allow_closed = False
            if allow_closed_kwarg and kwargs.get(allow_closed_kwarg):
                allow_closed = True
            ensure_market_open_or_raise_http(allow_closed=allow_closed)
            return await func(*args, **kwargs)
        return wrapper  # type: ignore[return-value]
    return decorator
