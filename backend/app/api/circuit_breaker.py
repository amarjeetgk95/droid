from fastapi import APIRouter
from app.services.market_service import MarketService
from app.models.market import ApiMeta, DataStatus
from datetime import datetime, timezone

router = APIRouter(prefix="/api/v1/circuit-breaker", tags=["circuit_breaker"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="system_circuit_breaker",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.LIVE,
    )


@router.get("/status")
async def get_circuit_breaker_status():
    """Get active circuit breaker state machine status."""
    service = MarketService()
    status = service.circuit_breaker.get_status()
    return {
        "data": status,
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.post("/reset")
async def reset_circuit_breaker():
    """Manually reset the circuit breaker to CLOSED state."""
    service = MarketService()
    service.circuit_breaker.reset()
    return {
        "data": service.circuit_breaker.get_status(),
        "error": None,
        "meta": _make_meta().model_dump(),
    }


@router.post("/trip")
async def trip_circuit_breaker():
    """Manually trip the circuit breaker to OPEN state (for testing / isolation)."""
    service = MarketService()
    service.circuit_breaker.trip(reason="Manual API trip")
    return {
        "data": service.circuit_breaker.get_status(),
        "error": None,
        "meta": _make_meta().model_dump(),
    }
