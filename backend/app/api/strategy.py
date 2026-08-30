from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from app.services.strategy_service import strategy_service
from app.models.strategy import StrategyPayload, MarketOutlook
from app.models.market import ApiMeta, DataStatus

router = APIRouter(prefix="/api/v1/strategy", tags=["strategy"])


def _make_meta() -> ApiMeta:
    return ApiMeta(
        provider="strategy_payoff_engine",
        timestamp=datetime.now(timezone.utc),
        status=DataStatus.DEMO,
    )


@router.post("/payoff")
async def calculate_strategy_payoff(payload: StrategyPayload):
    """Simulate dual-curve (At-Expiry & T+0) payoff and calculate portfolio Greeks."""
    try:
        result = await strategy_service.calculate_payoff(payload)
        return {
            "data": result.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates")
async def get_strategy_templates():
    """Retrieve catalog of pre-built institutional strategy templates."""
    try:
        templates = strategy_service.get_templates()
        return {
            "data": [t.model_dump(mode="json") for t in templates],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.api_route("/build-template", methods=["GET", "POST"])
async def build_strategy_template(
    template_id: str = Query(description="Strategy template ID e.g. bull_call_spread"),
    symbol: str = Query(default="NIFTY", description="Underlying symbol"),
):
    """Instantiate a pre-built template with live market strikes and simulated prices."""
    try:
        result = await strategy_service.build_template(template_id, symbol)
        return {
            "data": result.model_dump(mode="json"),
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/scanner")
async def scan_market_strategies(
    outlook: MarketOutlook | None = Query(default=None, description="Filter by market outlook"),
    min_pop: float = Query(default=35.0, description="Minimum Probability of Profit %"),
):
    """Scan and rank high-probability option strategies matching market outlook."""
    try:
        opportunities = await strategy_service.scan_strategies(outlook, min_pop)
        return {
            "data": [s.model_dump(mode="json") for s in opportunities],
            "error": None,
            "meta": _make_meta().model_dump(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
