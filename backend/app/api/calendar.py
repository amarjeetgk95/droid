from datetime import date, datetime, timezone
from fastapi import APIRouter, Query
from app.services.calendar_service import calendar_service
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/calendar", tags=["calendar"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="nse_official",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


@router.get("/holidays")
async def get_holidays(year: int | None = None):
    """List exchange holidays for current or specified year."""
    target_year = year or datetime.now(timezone.utc).year
    holidays = {
        d.isoformat(): name
        for d, name in calendar_service.NSE_HOLIDAYS.items()
        if d.year == target_year
    }
    return {
        "data": holidays,
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.get("/is-trading-day")
async def check_trading_day(target_date: date = Query(default_factory=lambda: datetime.now(timezone.utc).date())):
    """Check if target date is an exchange trading day."""
    is_trading = calendar_service.is_trading_day(target_date)
    holiday_name = calendar_service.get_holiday_name(target_date)
    return {
        "data": {
            "date": target_date.isoformat(),
            "is_trading_day": is_trading,
            "holiday_name": holiday_name,
        },
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.get("/session")
async def get_session_info(target_date: date = Query(default_factory=lambda: datetime.now(timezone.utc).date())):
    """Get complete trading session info for target date."""
    info = calendar_service.get_session_info(target_date)
    return {
        "data": {
            "is_trading_day": info.is_trading_day,
            "is_holiday": info.is_holiday,
            "is_weekend": info.is_weekend,
            "holiday_name": info.holiday_name,
            "is_special_session": info.is_special_session,
            "market_open": info.market_open.isoformat() if info.market_open else None,
            "market_close": info.market_close.isoformat() if info.market_close else None,
        },
        "error": None,
        "meta": _make_meta().model_dump(),
    }
