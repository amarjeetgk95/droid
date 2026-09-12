from fastapi import APIRouter
from app.api.envelope import envelope
from app.services.market_service import MarketService

router = APIRouter(prefix="/api/v1/circuit-breaker", tags=["circuit_breaker"])

_PROVIDER = "system_circuit_breaker"


@router.get("/status")
async def get_circuit_breaker_status():
    """Get active circuit breaker state machine status."""
    service = MarketService()
    return envelope(service.circuit_breaker.get_status(), provider=_PROVIDER)


@router.post("/reset")
async def reset_circuit_breaker():
    """Manually reset the circuit breaker to CLOSED state."""
    service = MarketService()
    service.circuit_breaker.reset()
    return envelope(service.circuit_breaker.get_status(), provider=_PROVIDER)


@router.post("/trip")
async def trip_circuit_breaker():
    """Manually trip the circuit breaker to OPEN state (for testing / isolation)."""
    service = MarketService()
    service.circuit_breaker.trip(reason="Manual API trip")
    return envelope(service.circuit_breaker.get_status(), provider=_PROVIDER)
