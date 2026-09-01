"""
Market State + Pipeline API — covers §6, §7, §22, §23, §28, §40 verification endpoints.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.core.market_state import capture_market_state
from app.services.trigger_gateway import trigger_gateway, TriggerType
from app.services.staleness_guard import check_staleness
from app.services.pricing_engine import calculate_deterministic_pricing, validate_risk_reward, calculate_position_size, validate_quantitative_confirmation
from app.services.execution_state_machine import execution_state_machine, ExecutionState
from app.services.observability import get_trace, get_all_traces, new_analysis_id, log_pipeline_event
from app.models.market import ApiMeta, DataStatus
from app.services.master_pipeline import master_pipeline
from app.services.trigger_gateway import TriggerType as _MasterTriggerType

router = APIRouter(prefix="/api/v1/pipeline", tags=["pipeline"])


def _meta() -> ApiMeta:
    return ApiMeta(provider="pipeline_engine", timestamp=datetime.now(timezone.utc), status=DataStatus.OFFLINE)


@router.post("/state/capture")
async def capture_state(
    symbol: str = Query(default="NIFTY"),
    current_price: float = Query(default=24750),
    atr: float = Query(default=38),
    regime: str = Query(default="TRENDING_UP"),
):
    """Capture immutable MarketState snapshot (§6)."""
    state = capture_market_state(
        symbol=symbol,
        current_price=current_price,
        atr=atr,
        regime=regime,
        mtf={"1m": "BULLISH", "5m": "BULLISH", "15m": "NEUTRAL_BULLISH", "1h": "BULLISH"},
        technical={"rsi": 64, "macd": "POSITIVE", "vwap": 24710, "atr": atr},
        direction_model={"prob_up": 0.68, "prob_down": 0.32},
        tsfm={"p10": 24695, "p50": 24782, "p90": 24835},
        orderflow={"ofi": 0.42, "volume_change": 0.31},
        options={"pcr": 1.12},
        futures={},
    )
    return {"data": state.model_dump(mode="json"), "error": None, "meta": _meta().model_dump()}


@router.post("/trigger/evaluate")
async def evaluate_trigger(
    symbol: str = Query(default="NIFTY"),
    trigger_type: str = Query(default="BREAKOUT"),
    significance: float | None = None,
):
    """Evaluate trigger gateway (§7)."""
    try:
        tt = TriggerType(trigger_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid trigger_type {trigger_type}. Allowed: {[t.value for t in TriggerType]}")
    snapshot = {"symbol": symbol, "price": 24750, "trigger": trigger_type, "sig": significance}
    should, reason = trigger_gateway.should_trigger(tt, symbol, snapshot, significance=significance)
    return {"data": {"should_trigger": should, "reason": reason, "trigger_type": tt.value}, "error": None, "meta": _meta().model_dump()}


class StalenessPayload(BaseModel):
    trigger_price: float
    trigger_atr: float
    trigger_timestamp: datetime
    trigger_state_version: int
    current_price: float
    trigger_regime: str | None = None
    current_regime: str | None = None
    max_drift_atr: float = 0.5


@router.post("/staleness/check")
async def check_stale(payload: StalenessPayload):
    """Check staleness guard (§23)."""
    res = check_staleness(
        trigger_price=payload.trigger_price,
        trigger_atr=payload.trigger_atr,
        trigger_timestamp=payload.trigger_timestamp,
        trigger_state_version=payload.trigger_state_version,
        trigger_regime=payload.trigger_regime,
        current_price=payload.current_price,
        current_regime=payload.current_regime,
        max_drift_atr=payload.max_drift_atr,
    )
    return {"data": res.model_dump(), "error": None, "meta": _meta().model_dump()}


class PricingPayload(BaseModel):
    bias: str
    current_price: float
    p10: float
    p50: float
    p90: float
    vwap: float | None = None
    atr: float | None = None
    k: float = 1.0


@router.post("/pricing/calculate")
async def calc_pricing(payload: PricingPayload):
    """Deterministic pricing (§25)."""
    try:
        res = calculate_deterministic_pricing(
            bias=payload.bias,  # type: ignore
            current_price=payload.current_price,
            p10=payload.p10,
            p50=payload.p50,
            p90=payload.p90,
            vwap=payload.vwap,
            atr=payload.atr,
            k=payload.k,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": res.__dict__, "error": None if res.valid else res.reason, "meta": _meta().model_dump()}


@router.post("/risk/validate")
async def risk_validate(
    symbol: str = Query(default="NIFTY"),
    ai_bias: str = Query(default="BUY"),
    prob_up: float | None = None,
    prob_down: float | None = None,
    p50: float | None = None,
    current_price: float | None = None,
):
    res, msg = validate_quantitative_confirmation(ai_bias, prob_up, prob_down, p50=p50, current_price=current_price)
    return {"data": {"valid": res, "reason": msg}, "error": None, "meta": _meta().model_dump()}


@router.post("/execution/signal")
async def create_execution_signal(
    symbol: str = Query(default="NIFTY"),
    side: str = Query(default="BUY"),
    quantity: int = Query(default=50),
    state_version: int | None = None,
):
    analysis_id = new_analysis_id()
    order = execution_state_machine.create_signal(symbol, side, quantity, analysis_id, state_version)
    log_pipeline_event(analysis_id, "SIGNAL_CREATED", {"symbol": symbol, "side": side, "quantity": quantity})
    return {"data": order.model_dump(mode="json"), "error": None, "meta": _meta().model_dump()}


@router.post("/execution/{order_id}/transition")
async def transition_execution(order_id: str, to_state: str, event_id: str | None = None):
    try:
        ts = ExecutionState(to_state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid state {to_state}")
    try:
        order = execution_state_machine.transition(order_id, ts, event_id=event_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"data": order.model_dump(mode="json"), "error": None, "meta": _meta().model_dump()}


@router.get("/execution/orders")
async def list_execution_orders():
    orders = execution_state_machine.list_orders()
    return {"data": [o.model_dump(mode="json") for o in orders], "error": None, "meta": _meta().model_dump()}


@router.get("/observability/trace/{analysis_id}")
async def get_pipeline_trace(analysis_id: str):
    trace = get_trace(analysis_id)
    if not trace:
        raise HTTPException(status_code=404, detail="trace not found")
    return {"data": {"analysis_id": analysis_id, "events": trace}, "error": None, "meta": _meta().model_dump()}


@router.get("/observability/traces")
async def list_traces(limit: int = Query(default=20, le=100)):
    traces = get_all_traces(limit=limit)
    return {"data": traces, "error": None, "meta": _meta().model_dump()}


class MasterPipelineRequest(BaseModel):
    symbol: str = "NIFTY"
    current_price: float = 24750
    atr: float = 38
    regime: str = "TRENDING_UP"
    mtf: dict | None = None
    technical: dict | None = None
    direction_model: dict | None = None
    tsfm: dict | None = None
    orderflow: dict | None = None
    options: dict | None = None
    futures: dict | None = None
    news: list | None = None
    trigger_type: str = "MANUAL_ANALYSIS"
    ai_bias: str | None = None
    ai_confidence_breakdown: dict | None = None
    ai_raw_response: str | dict | None = None
    current_market_price: float | None = None
    position_context: dict | None = None
    account_equity: float = 1000000


@router.post("/trade-decision")
async def master_trade_decision(payload: MasterPipelineRequest):
    """
    Master trade-decision pipeline §45 — full lifecycle:
    market data → technical → direction → TSFM → trigger → state version
    → router → AI validation → stale check → quant alignment → deterministic
    pricing → R:R → risk → position → execution SM → broker feedback.
    Never forces a trade; returns explicit outcome states.
    """
    try:
        try:
            tt = _MasterTriggerType(payload.trigger_type)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"invalid trigger_type {payload.trigger_type}")
        result = await master_pipeline.evaluate(
            symbol=payload.symbol,
            current_price=payload.current_price,
            atr=payload.atr,
            regime=payload.regime,
            mtf=payload.mtf,
            technical=payload.technical,
            direction_model=payload.direction_model,
            tsfm=payload.tsfm,
            orderflow=payload.orderflow,
            options=payload.options,
            futures=payload.futures,
            news=payload.news,
            trigger_type=tt,
            ai_bias=payload.ai_bias,
            ai_confidence_breakdown=payload.ai_confidence_breakdown,
            ai_raw_response=payload.ai_raw_response,
            current_market_price=payload.current_market_price,
            position_context=payload.position_context,
            account_equity=payload.account_equity,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"data": result, "error": None if result.get("outcome") in ("SIGNAL_CREATED", "HOLD", "NO_TRADE", "WAIT_FOR_CONFIRMATION") else result.get("reason"), "meta": _meta().model_dump()}
