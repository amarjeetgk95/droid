"""
Institutional-Grade Trading Intelligence — Unified API
Exposes: instruments, market intelligence, breakout, signal, audit, health, telegram, pipeline ingest
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Request, Header, Query
from pydantic import BaseModel

from app.institutional.instrument_registry import asset_registry, CapabilityMap
from app.institutional.clocks import get_session_clock
from app.institutional.feed_circuit import feed_circuit
from app.institutional.sequence import get_sequence_validator
from app.institutional.snapshot_buffer import synchronized_buffer
from app.institutional.market_intelligence import market_intelligence_engine
from app.institutional.breakout_engine import breakout_engine, short_horizon_strategy, continuation_strategy
from app.institutional.ai_confirmation import ai_confirmation_engine, AIConfirmationRequest
from app.institutional.signal import signal_fsm, create_signal, check_ttl
from app.institutional.decimal_types import D, normalize_price_to_tick, validate_quantity, compute_notional
from app.institutional.portfolio_risk import institutional_portfolio_engine, PortfolioState, PositionExposure
from app.institutional.audit import audit_trail
from app.institutional.pipeline import institutional_pipeline
from app.institutional.telegram import telegram_link_manager, telegram_outbound_queue, verify_telegram_secret, handle_telegram_update, is_duplicate_update
from app.core.config import settings

router = APIRouter(prefix="/api/v1/institutional", tags=["institutional"])


# ── Instruments ──────────────────────────────────────────────────────
@router.get("/instruments")
def list_instruments():
    return {"instruments": [p.to_dict() for p in asset_registry.all_profiles()], "count": len(asset_registry.all_profiles())}

@router.get("/instruments/{instrument_id}")
def get_instrument(instrument_id: str):
    prof = asset_registry.get(instrument_id)
    if not prof: raise HTTPException(404, f"instrument {instrument_id} not found")
    return prof.to_dict()

@router.get("/instruments/{instrument_id}/capabilities")
def get_capabilities(instrument_id: str):
    prof = asset_registry.get(instrument_id)
    if not prof: raise HTTPException(404, "not found")
    return {"instrument_id": prof.instrument_id, "available_modules": sorted(CapabilityMap.available_modules(instrument_id)), "contract_spec": prof.contract_spec.to_dict() if prof.contract_spec else None}

@router.post("/instruments/{instrument_id}/contract-spec/refresh")
def refresh_contract_spec(instrument_id: str, meta: dict[str, Any]):
    prof = asset_registry.get(instrument_id)
    if not prof: raise HTTPException(404, "not found")
    asset_registry.update_from_broker_metadata(instrument_id, meta)
    return {"status": "updated", "contract_spec": prof.contract_spec.to_dict() if prof.contract_spec else None}


# ── Market Intelligence ──────────────────────────────────────────────
class MIRequest(BaseModel):
    instrument_id: str
    spot_price: float | None = None
    vwap: float | None = None
    futures_price: float | None = None
    volumes: dict[str, Any] | None = None
    oi_data: dict[str, Any] | None = None
    options_data: dict[str, Any] | None = None
    support_resistance: dict | None = None
    multi_timeframe: dict[str, str] | None = None
    volatility: dict[str, Any] | None = None
    liquidity: dict[str, Any] | None = None
    funding: dict[str, Any] | None = None
    data_health: str = "LIVE"
    feed_health: str = "HEALTHY"

@router.post("/market-intelligence/evaluate")
def evaluate_market_intelligence(req: MIRequest):
    # Handle NOT_APPLICABLE for BTC — ignore forced PCR
    prof = asset_registry.get(req.instrument_id)
    if prof and prof.asset_class == "CRYPTO" and req.options_data and "pcr" in req.options_data:
        req.options_data = None
    ctx = market_intelligence_engine.evaluate(
        instrument_id=req.instrument_id,
        spot_price=D(req.spot_price) if req.spot_price is not None else None,
        vwap=D(req.vwap) if req.vwap is not None else None,
        futures_price=D(req.futures_price) if req.futures_price is not None else None,
        volumes=req.volumes, oi_data=req.oi_data, options_data=req.options_data,
        support_resistance=req.support_resistance, multi_timeframe=req.multi_timeframe,
        volatility=req.volatility, liquidity=req.liquidity, funding=req.funding,
        data_health=req.data_health, feed_health=req.feed_health,
    )
    return ctx.to_dict()

# ── Breakout + Horizons ──────────────────────────────────────────────
class BreakoutRequest(BaseModel):
    instrument_id: str
    breakout_level: str  # decimal string
    current_price: str
    close_confirmed: bool = False
    volume_expansion: bool = False
    atr: str | None = None
    momentum_accel: bool = False
    data_health: str = "LIVE"
    feed_health: str = "HEALTHY"
    # Minimal context for MI
    multi_timeframe: dict[str, str] | None = None
    vwap: str | None = None
    volumes: dict | None = None
    options_data: dict | None = None

@router.post("/breakout/evaluate")
def evaluate_breakout(req: BreakoutRequest):
    # Build MI first
    ctx = market_intelligence_engine.evaluate(
        instrument_id=req.instrument_id,
        spot_price=D(req.current_price),
        vwap=D(req.vwap) if req.vwap else None,
        volumes=req.volumes, options_data=req.options_data,
        multi_timeframe=req.multi_timeframe,
        data_health=req.data_health, feed_health=req.feed_health,
    )
    sig = breakout_engine.evaluate(ctx, breakout_level=D(req.breakout_level), current_price=D(req.current_price), close_confirmed=req.close_confirmed, volume_expansion=req.volume_expansion)
    atr_d = D(req.atr) if req.atr else None
    short_out = short_horizon_strategy.evaluate(ctx, breakout_level=D(req.breakout_level), current_price=D(req.current_price), atr=atr_d, momentum_accel=req.momentum_accel, volume_expansion=req.volume_expansion, close_confirmed=req.close_confirmed)
    cont_out = continuation_strategy.evaluate(ctx, breakout_level=D(req.breakout_level), current_price=D(req.current_price), atr=atr_d, close_confirmed=req.close_confirmed, volume_expansion=req.volume_expansion)
    return {
        "market_context": ctx.to_dict(),
        "breakout": {"instrument_id": sig.instrument_id, "direction": sig.direction, "status": sig.status, "confidence": sig.confidence, "false_breakout_risk": sig.false_breakout_risk, "supporting": sig.supporting, "conflicts": sig.conflicts, "reason": sig.reason},
        "short_horizon": short_out.to_dict(),
        "continuation": cont_out.to_dict(),
        "horizon_separation_note": "10-minute and <2h continuation evaluated separately — can be CONFIRMED/WATCH independently (§34)",
    }

# ── Signal FSM ───────────────────────────────────────────────────────
class SignalCreateRequest(BaseModel):
    instrument_id: str
    strategy: str = "BREAKOUT"
    direction: Literal["BULLISH","BEARISH","NEUTRAL"] = "BULLISH"
    short_horizon: dict | None = None
    continuation: dict | None = None
    ai: dict | None = None
    ttl_ms: int = 5000

@router.post("/signals")
def create_signal_endpoint(req: SignalCreateRequest):
    from app.institutional.clocks import get_session_clock
    clock = get_session_clock(req.instrument_id)
    if clock.current_state() == "CLOSED":
        raise HTTPException(status_code=400, detail=f"Signal creation blocked: market is closed for {req.instrument_id}")
    sig = create_signal(instrument_id=req.instrument_id, strategy=req.strategy, direction=req.direction, short_horizon=req.short_horizon, continuation=req.continuation, ai=req.ai, ttl_ms=req.ttl_ms)
    signal_fsm.register(sig)
    return sig.to_dict()

@router.get("/signals/active")
async def get_active_signals(
    instrument: str | None = Query(None, description="Filter by NIFTY/BANKNIFTY/SENSEX/BTCUSD"),
    status: str | None = Query(None, description="Filter by CONFIRMED/WATCH/POSSIBLE_BREAKOUT etc"),
):
    from app.institutional.signal_center import signal_center
    data = await signal_center.active_setups(instrument=instrument, status=status)
    return {"signals": data, "count": len(data), "generated_at_ms": time.time() * 1000}

@router.get("/signals/history")
async def get_signals_history(limit: int = 20):
    from app.institutional.audit import audit_trail
    return {"records": audit_trail.recent(limit)}

@router.get("/signals/{signal_id}")
def get_signal(signal_id: str):
    sig = signal_fsm.get(signal_id)
    if not sig: raise HTTPException(404, "signal not found")
    return {**sig.to_dict(), "is_expired": sig.is_expired(), "ttl_remaining_ms": sig.ttl_remaining_ms(), "state_history": sig.state_history}

@router.post("/signals/{signal_id}/transition")
def transition_signal(signal_id: str, to_state: str):
    ok, err = signal_fsm.transition(signal_id, to_state)  # type: ignore
    if not ok: raise HTTPException(400, err or "transition failed")
    sig = signal_fsm.get(signal_id)
    return sig.to_dict() if sig else {"error": "not found"}

@router.post("/signals/{signal_id}/cas-execution")
def cas_execution(signal_id: str):
    ok, err = signal_fsm.cas_to_execution_pending(signal_id)
    if not ok: raise HTTPException(400, err or "CAS failed")
    sig = signal_fsm.get(signal_id)
    return {"status": "EXECUTION_PENDING", "signal": sig.to_dict() if sig else None}

@router.get("/signals/{signal_id}/ttl-check")
def ttl_check(signal_id: str):
    sig = signal_fsm.get(signal_id)
    if not sig: raise HTTPException(404, "not found")
    ok, err = check_ttl(sig, "api_ttl_check")
    return {"signal_id": signal_id, "is_expired": sig.is_expired(), "ttl_remaining_ms": sig.ttl_remaining_ms(), "valid": ok, "error": err, "fsm_state": sig.fsm_state}

# ── Synchronized Snapshot ────────────────────────────────────────────
@router.post("/snapshot/ingest")
def ingest_snapshot_event(event: dict[str, Any]):
    # event keys: instrument_id, canonical_timestamp_utc, price etc.
    from app.institutional.events import InstrumentEvent
    iid = event.get("instrument_id", "NIFTY")
    asset_class = asset_registry.get(iid).asset_class if asset_registry.get(iid) else "INDEX"
    seq = int(event.get("sequence_id", int(time.time()*1000) % 100000))
    e = InstrumentEvent.create(instrument_id=iid, asset_class=asset_class, canonical_timestamp_utc=int(event.get("canonical_timestamp_utc", int(time.time()*1000))), sequence_id=seq, price=event.get("price"))
    synchronized_buffer.ingest_sync(e)
    return {"status": "ingested", "event_id": e.event_id}

@router.get("/snapshot/synchronized")
def get_synchronized(instruments: str = Query(..., description="comma separated e.g. NIFTY,BANKNIFTY"), threshold_ms: int = 500):
    ids = [s.strip() for s in instruments.split(",") if s.strip()]
    snap = synchronized_buffer.get_synchronized(ids, threshold_ms=threshold_ms)
    return {"snapshot_timestamp": snap.snapshot_timestamp, "delta_ms": snap.delta_ms, "status": snap.status, "reason": snap.reason, "entries": {k: {"price": v.event.price, "canonical_timestamp_utc": v.event.canonical_timestamp_utc} for k, v in snap.entries.items()}}

@router.get("/snapshot/health")
def snapshot_health():
    return synchronized_buffer.health()

# ── Feed Health / Circuit Breaker ────────────────────────────────────
@router.get("/feed/health")
def feed_health():
    return {"feeds": {k: feed_circuit.to_dict(k) for k in asset_registry.all_ids()}, "detail": {k: v.__dict__ for k, v in feed_circuit.all_states().items()}}

@router.get("/feed/{instrument_id}/health")
def feed_health_one(instrument_id: str):
    return feed_circuit.to_dict(instrument_id)

@router.post("/feed/{instrument_id}/trip")
def feed_trip(instrument_id: str, anomaly: str = "MISSING", reason: str = "manual trip"):
    st = feed_circuit.trip(instrument_id, anomaly=anomaly, reason=reason)
    return feed_circuit.to_dict(instrument_id)

@router.post("/feed/{instrument_id}/resync-request")
def feed_resync_request(instrument_id: str):
    st = feed_circuit.request_resync(instrument_id)
    return feed_circuit.to_dict(instrument_id)

@router.post("/feed/{instrument_id}/authoritative-snapshot")
def feed_authoritative_snapshot(instrument_id: str, snapshot_timestamp_ms: int, sequence_id: int):
    st = feed_circuit.on_authoritative_snapshot(instrument_id, snapshot_timestamp_ms, sequence_id)
    return feed_circuit.to_dict(instrument_id)

# ── Decimal / Contract Validation ────────────────────────────────────
@router.post("/contract/validate")
def validate_contract(instrument_id: str, price: str, quantity: str):
    prof = asset_registry.get(instrument_id)
    if not prof: raise HTTPException(404, "instrument not found")
    spec = prof.contract_spec
    if not spec: raise HTTPException(400, "contract spec missing")
    # Tick validation
    try:
        quantized = normalize_price_to_tick(price, spec.tick_size)
    except Exception as e:
        return {"valid": False, "reason": f"ORDER_INVALID_PRICE {e}", "tick_size": str(spec.tick_size)}
    ok_qty, reason = validate_quantity(quantity, spec.min_order_qty, spec.quantity_step, spec.lot_size if instrument_id != "BTCUSD" else None)
    # Exposure
    exp = None
    try:
        from app.institutional.decimal_types import normalize_exposure
        exp = normalize_exposure(price, quantity, spec.contract_multiplier)
    except Exception:
        pass
    return {
        "valid": ok_qty and D(quantized) == D(price),
        "quantized_price": format(quantized, 'f'),
        "price_tick_aligned": D(quantized) == D(price),
        "quantity_valid": ok_qty,
        "quantity_reason": reason,
        "contract_spec": spec.to_dict(),
        "exposure": exp,
    }

@router.post("/decimal/exposure")
def compute_exposure(instrument_id: str, price: str, quantity: str):
    prof = asset_registry.get(instrument_id)
    if not prof: raise HTTPException(404, "not found")
    spec = prof.contract_spec
    if not spec: raise HTTPException(400, "spec missing")
    mult = spec.contract_multiplier
    n = compute_notional(price, quantity, mult)
    return {"notional": format(n.value, 'f'), "price": price, "quantity": quantity, "multiplier": str(mult), "serialized": {"price": price, "quantity": quantity}}

# ── AI Confirmation ──────────────────────────────────────────────────
class AIConfirmRequest(BaseModel):
    instrument_id: str
    short_horizon: dict | None = None
    continuation: dict | None = None
    market_context: dict | None = None
    mock_ai_response: dict | str | None = None  # for testing without live AI

@router.post("/ai/confirm")
async def ai_confirm(req: AIConfirmRequest):
    # Build minimal request from provided context or synthesize
    ctx_dict = req.market_context or {}
    # Determine regime etc.
    asset_class = asset_registry.get(req.instrument_id).asset_class if asset_registry.get(req.instrument_id) else "INDEX"
    session_state = get_session_clock(req.instrument_id).current_state()
    ai_req = AIConfirmationRequest(
        instrument=req.instrument_id, asset_class=asset_class, market_session=session_state,
        data_freshness=ctx_dict.get("data_freshness", "LIVE"), data_quality=ctx_dict.get("data_quality", "VALID"),
        market_regime=ctx_dict.get("technical", {}).get("regime", "RANGING") if isinstance(ctx_dict.get("technical"), dict) else "RANGING",
        price_action=ctx_dict.get("price_action", {}), structure=ctx_dict.get("price_action", {}).get("structure", "UNKNOWN") if isinstance(ctx_dict.get("price_action"), dict) else "UNKNOWN",
        momentum=ctx_dict.get("price_action", {}).get("momentum", "NEUTRAL") if isinstance(ctx_dict.get("price_action"), dict) else "NEUTRAL",
        volume=ctx_dict.get("participation", {}).get("volume", "UNKNOWN") if isinstance(ctx_dict.get("participation"), dict) else "UNKNOWN",
        supporting_evidence=ctx_dict.get("supporting_evidence", []), contradictory_evidence=ctx_dict.get("conflicting_evidence", []),
        proposed_setup=req.short_horizon,
    )
    if req.mock_ai_response is not None:
        # Call with mock provider that returns mock_ai_response
        async def mock_provider(prompt_ctx):
            return req.mock_ai_response
        resp = await ai_confirmation_engine.confirm(ai_req, ai_provider_callable=mock_provider)
    else:
        resp = await ai_confirmation_engine.confirm(ai_req, ai_provider_callable=None)
    return {"short_horizon": resp.short_horizon.to_dict(), "continuation": resp.continuation.to_dict(), "overall_assessment": resp.overall_assessment, "ai_status": resp.ai_status, "error": resp.error}

# ── Portfolio Risk ───────────────────────────────────────────────────
class PortfolioRiskRequest(BaseModel):
    new_order_instrument: str
    new_order_notional: str
    new_order_margin: str
    side: Literal["BUY","SELL"] = "BUY"
    existing_positions: list[dict] | None = None  # each {instrument_id, notional, margin}
    limits: dict | None = None

@router.post("/risk/portfolio-evaluate")
def portfolio_risk_eval(req: PortfolioRiskRequest):
    portfolio = PortfolioState()
    if req.existing_positions:
        for p in req.existing_positions:
            portfolio.positions.append(PositionExposure(instrument_id=p["instrument_id"], notional=D(p["notional"]), margin=D(p.get("margin", p["notional"]))))
        portfolio.compute()
        # infer concurrent trades
        portfolio.concurrent_trades = len(portfolio.positions)
    inp = None
    from app.institutional.portfolio_risk import PortfolioRiskInput
    inp = PortfolioRiskInput(new_order_instrument=req.new_order_instrument, new_order_notional=D(req.new_order_notional), new_order_margin=D(req.new_order_margin), side=req.side, portfolio=portfolio, limits=req.limits or {})
    decision = institutional_portfolio_engine.evaluate(inp)
    return {"result": decision.result, "reason": decision.reason, "failed_check": decision.failed_check, "checks": [{"name": c.name, "passed": c.passed, "reason": c.reason} for c in decision.checks], "portfolio": {"gross": format(portfolio.total_gross_notional, 'f'), "net": format(portfolio.total_net_notional, 'f'), "margin_used": format(portfolio.margin_used, 'f')}}

# ── Audit ────────────────────────────────────────────────────────────
@router.get("/audit/recent")
def audit_recent(limit: int = 20):
    return {"records": audit_trail.recent(limit)}

@router.get("/audit/{signal_id}")
def audit_get(signal_id: str):
    rec = audit_trail.reconstruct(signal_id)
    if not rec: raise HTTPException(404, "audit not found for signal")
    return rec

# ── Data Health (§68, §72) ───────────────────────────────────────────
@router.get("/health/data")
def data_health():
    now_ms = int(time.time()*1000)
    # No synthetic seeding — live feed only. Empty buffer correctly shows DISCONNECTED/CLOSED.
    feeds = {iid: feed_circuit.to_dict(iid) for iid in asset_registry.all_ids()}
    # Per-feed last event etc. from synchronized_buffer
    snap_health = synchronized_buffer.health()
    # Derive LIVE/STALE etc.
    out = {}
    for iid in asset_registry.all_ids():
        fc = feed_circuit.snapshot(iid)
        age_info = snap_health.get(iid, {})
        age_ms = age_info.get("age_ms")
        prof = asset_registry.get(iid)
        sess_state = get_session_clock(iid).current_state(now_ms=now_ms)
        status = "LIVE"
        if fc.health == "FEED_DEGRADED": status = "FEED_DEGRADED"
        elif age_ms is not None and age_ms > 5000: status = "STALE"
        elif age_ms is not None and age_ms > 2000: status = "RECENT"
        elif age_ms is None:
            # Indian CLOSED with no tick is not a failure — show CLOSED; BTC never CLOSED
            if prof and prof.pipeline == "INDIAN_EQUITY" and sess_state == "CLOSED":
                status = "CLOSED"
            else:
                status = "DISCONNECTED"
        out[iid] = {
            "feed_health": fc.health,
            "data_health": status,
            "last_event_age_ms": age_ms,
            "last_event_canonical_ms": age_info.get("canonical_timestamp_utc"),
            "session": get_session_clock(iid).session_info(now_ms=now_ms),
            "sequence_last": get_sequence_validator(iid).last_seq,
            "clock_sync": "VALID",  # placeholder — would check drift
            "snapshot_valid": status == "LIVE",
            "contract_valid": asset_registry.get(iid).contract_spec is not None,
        }
    return {"data_health": out, "generated_at_ms": now_ms}

# ── Institutional Pipeline Ingest (canonical event → full hierarchy) ──
@router.post("/pipeline/ingest")
async def pipeline_ingest(event: dict[str, Any], mock_ai_response: dict | str | None = None):
    """
    Unified ingestion: raw tick → full institutional pipeline (§80)
    Pass mock_ai_response for testing AI path without live provider.
    """
    async def mock_provider(prompt_ctx):
        return mock_ai_response
    provider = mock_provider if mock_ai_response is not None else None
    result = await institutional_pipeline.process_event(event, ai_provider_callable=provider)
    return result

# ── Telegram Webhook & Linking ───────────────────────────────────────
@router.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token")):
    expected = settings.telegram_secret_token
    if expected and not verify_telegram_secret(x_telegram_bot_api_secret_token, expected):
        raise HTTPException(status_code=403, detail="invalid secret token")
    body = await request.json()
    # Non-blocking: deduplicate + enqueue
    update_id = body.get("update_id")
    if update_id is not None and is_duplicate_update(update_id):
        return {"status": "ok", "detail": "duplicate ignored"}
    # Enqueue for background worker — here we just log and acknowledge HTTP 200 immediately (§56)
    # In production push to Redis/ARQ queue
    handle = handle_telegram_update(body, secret_valid=True)
    # If message needs enqueuing to outbound, worker will pick up
    # For now just return 200 without expensive work
    return {"status": "ok", "update_id": update_id, "enqueued": True}

@router.post("/telegram/link/generate")
def telegram_link_generate(user_id: str, ttl_seconds: int = 600):
    # Validate TTL 5-10 min per §59
    if not (300 <= ttl_seconds <= 600):
        raise HTTPException(400, "TTL must be 300-600 seconds")
    token = telegram_link_manager.generate_link_token(user_id, ttl_seconds=ttl_seconds)
    bot = settings.telegram_bot_username or "your_bot"
    url = f"https://t.me/{bot}?start={token}"
    return {"token": token, "url": url, "ttl_seconds": ttl_seconds, "allowed_chars": "A-Za-z0-9_-", "max_length": 64}

@router.post("/telegram/link/verify")
def telegram_link_verify(token: str, telegram_chat_id: str):
    ok, info = telegram_link_manager.verify_and_bind(token, telegram_chat_id)
    if not ok: raise HTTPException(400, info)
    return {"status": "linked", "user_id": info, "telegram_chat_id": telegram_chat_id}

@router.get("/telegram/link/status")
def telegram_link_status(user_id: str | None = None, telegram_chat_id: str | None = None):
    if user_id: return {"binding": telegram_link_manager.get_binding(user_id)}
    if telegram_chat_id:
        ok, uid = telegram_link_manager.is_authorized(telegram_chat_id)
        return {"authorized": ok, "user_id": uid}
    raise HTTPException(400, "provide user_id or telegram_chat_id")

@router.post("/telegram/send")
async def telegram_send(chat_id: str, text: str, parse_mode: str = "Markdown"):
    from app.institutional.telegram import TelegramOutbound
    # Must pass through rate-limited queue (§58)
    msg = TelegramOutbound(chat_id=chat_id, text=text, parse_mode=parse_mode)
    await telegram_outbound_queue.enqueue(msg)
    return {"status": "enqueued", "chat_id": chat_id}

@router.get("/telegram/commands")
def telegram_commands():
    from app.institutional.telegram import TELEGRAM_COMMANDS
    return {"commands": TELEGRAM_COMMANDS}

@router.get("/dashboard/market-intelligence")
def dashboard_market_intelligence(instrument_id: str = "NIFTY"):
    """
    UI — Market Intelligence panel (§71)
    """
    # Provide current MI based on last snapshot
    latest = synchronized_buffer.get_latest(instrument_id)
    spot = None
    if latest:
        try: spot = D(latest.event.price) if latest.event.price else None
        except: spot = None
    prof = asset_registry.get(instrument_id)
    ctx = market_intelligence_engine.evaluate(instrument_id=instrument_id, spot_price=spot)
    sig = breakout_engine.evaluate(ctx)
    # Use current price for short/continuation
    atr = D("50")  # placeholder; real would come from technical engine
    short_out = short_horizon_strategy.evaluate(ctx, current_price=spot, atr=atr)
    cont_out = continuation_strategy.evaluate(ctx, current_price=spot, atr=atr)
    return {
        "instrument": instrument_id,
        "regime": ctx.technical.get("regime"),
        "price_action": ctx.price_action,
        "bullish_score": ctx.scores.get("bullish_score"),
        "bearish_score": ctx.scores.get("bearish_score"),
        "breakout_pressure": ctx.scores.get("breakout_pressure"),
        "false_breakout_risk": ctx.scores.get("false_breakout_risk"),
        "short_horizon": short_out.to_dict(),
        "continuation": cont_out.to_dict(),
        "max_holding": "< 2 Hours",
        "cross_market": ctx.cross_market,
        "synchronization_status": ctx.synchronization_status,
    }

@router.get("/dashboard/data-health")
def dashboard_data_health():
    # §72 Data Health panel
    return await_data_health_proxy()

def await_data_health_proxy():
    # synchronous proxy to data_health logic
    now_ms = int(time.time()*1000)
    snap_health = synchronized_buffer.health()
    out = {}
    for iid in asset_registry.all_ids():
        fc = feed_circuit.snapshot(iid)
        age = snap_health.get(iid, {}).get("age_ms")
        if fc.health == "FEED_DEGRADED": st = "FEED_DEGRADED"
        elif age is None: st = "DISCONNECTED"
        elif age > 5000: st = "STALE"
        elif age > 2000: st = "RECENT"
        else: st = "LIVE"
        clock_sync = "VALID"
        seq_valid = "VALID"
        snap_valid = st == "LIVE"
        contract_valid = asset_registry.get(iid).contract_spec is not None
        out[iid] = {"status": st, "feed": fc.health}
        out_overall = {"clock_sync": clock_sync, "sequence": seq_valid, "snapshot": "VALID" if all(synchronized_buffer.get_latest(i) for i in asset_registry.all_ids()) else "MISSING", "contracts": "VALID" if contract_valid else "INVALID"}
    # Build UI shape
    return {"data_health": out, "overall": out_overall, "generated_at_ms": now_ms}

# ── Calls & Puts Intelligence (§12) ───────────────────────────────────
@router.get("/calls-puts/{underlying}/full")
async def calls_puts_full(underlying: str, expiry: str | None = None):
    from app.institutional.options_intelligence import get_calls_puts_full
    underlying = underlying.upper().replace(" 50", "").replace("NIFTY 50", "NIFTY")
    if underlying.upper() in ("BTCUSD", "BTC", "BTCUSDT"):
        underlying = "BTCUSD"
    try:
        data = await get_calls_puts_full(underlying, expiry)
        return data
    except Exception as e:
        raise HTTPException(500, f"calls-puts failed for {underlying}: {e}")

@router.get("/dashboard/signal-ttl/{signal_id}")
def dashboard_signal_ttl(signal_id: str):
    sig = signal_fsm.get(signal_id)
    if not sig: raise HTTPException(404, "not found")
    return {
        "signal_id": signal_id,
        "created_at_utc": sig.created_at_utc,
        "expires_at_utc": sig.expires_at_utc,
        "ttl_ms": sig.ttl_ms,
        "ttl_remaining_ms": sig.ttl_remaining_ms(),
        "is_expired": sig.is_expired(),
        "fsm_state": sig.fsm_state,
        "validation_status": sig.validation_status,
        "risk_status": sig.risk_status,
    }


# ── Consolidated Full Market Intelligence Endpoint ────────────────────
@router.get("/market-intelligence/{instrument_id}/full")
async def get_full_mi(instrument_id: str):
    prof = asset_registry.get(instrument_id)
    if not prof:
        raise HTTPException(404, f"instrument {instrument_id} not found")
    now_ms = int(time.time() * 1000)
    iid = prof.instrument_id

    # Determine spot price from latest buffer if available
    latest = synchronized_buffer.get_latest(iid)
    spot: Decimal | None = None
    last_update_ms = now_ms
    if latest:
        try:
            spot = D(latest.event.price) if latest.event.price else None
            last_update_ms = latest.event.canonical_timestamp_utc
        except Exception:
            spot = None

    # Live fetch — no synthetic demo. Try MarketService live quote, then Binance for BTC.
    used_synthetic = False
    is_synthetic_fallback = False
    if spot is None:
        try:
            from app.services.market_service import MarketService
            from app.models.market import DataStatus
            svc = MarketService()
            q = await svc.get_quote(iid)
            if q and getattr(q, 'ltp', None) is not None and getattr(q, 'status', None) != DataStatus.OFFLINE and getattr(q, 'provider', '') != 'fallback':
                spot = D(str(q.ltp))
                try:
                    last_update_ms = int(q.timestamp.timestamp() * 1000) if getattr(q, 'timestamp', None) else now_ms
                except Exception:
                    pass
            elif iid == "BTCUSD":
                # Secondary: Binance ticker for crypto
                try:
                    from app.services.binance_service import binance_service
                    ticker = await binance_service.get_ticker("BTCUSDT")
                    if ticker and getattr(ticker, 'price', None) and ticker.price > 0 and getattr(getattr(ticker, 'status', None), 'value', '') == "LIVE":
                        spot = D(str(ticker.price))
                        try:
                            last_update_ms = int(ticker.last_updated.timestamp() * 1000) if getattr(ticker, 'last_updated', None) else now_ms
                        except Exception:
                            pass
                        try:
                            from app.institutional.events import InstrumentEvent
                            synth = InstrumentEvent.create(instrument_id=iid, asset_class="CRYPTO", symbol="BTCUSDT", price=spot, exchange_timestamp_utc=last_update_ms, canonical_timestamp_utc=last_update_ms, is_synthetic=False)
                            synchronized_buffer.push(synth)
                        except Exception:
                            pass
                except Exception:
                    pass
        except Exception as e:
            try:
                import structlog as _sl
                _sl.get_logger().warning("mi_live_fetch_failed", instrument=iid, error=str(e)[:150])
            except Exception:
                pass
        if spot is None:
            # No live data available — keep None, frontend will show STALE/— (no legacy 24560 demo)
            used_synthetic = False
            is_synthetic_fallback = False

    clock = get_session_clock(iid)
    clk_info = clock.session_info(now_ms) if hasattr(clock, "session_info") else {}
    feed_snap = feed_circuit.snapshot(iid)
    seq_val = get_sequence_validator(iid)

    ctx = market_intelligence_engine.evaluate(instrument_id=iid, spot_price=spot)
    sig = breakout_engine.evaluate(ctx)

    atr = None
    try:
        from app.services.regime_service import regime_service
        ind = await regime_service.get_technical_indicators(iid)
        if ind and ind.atr_14 > 0:
            atr = D(str(ind.atr_14))
    except Exception:
        pass
    # Short/continuation require live price — if no live, return WATCH (no synthetic)
    if spot is not None:
        try:
            short_out = short_horizon_strategy.evaluate(ctx, current_price=spot, atr=atr)
            cont_out = continuation_strategy.evaluate(ctx, current_price=spot, atr=atr)
        except Exception as _e:
            # Fallback to WATCH on evaluation error (e.g. no price)
            class _WatchFallback:
                def to_dict(self_inner):
                    return {"status": "WATCH", "reason": f"no live price: {_e}", "confidence": 0, "direction": "NEUTRAL", "horizon_minutes": 10, "entry_zone": [], "stop_loss": "0", "target_zone": [], "false_breakout_risk": 0, "max_holding_minutes": 120, "invalidation": "—"}
            short_out = _WatchFallback()
            cont_out = _WatchFallback()
    else:
        class _NoLiveFallback:
            def to_dict(self_inner):
                return {"status": "WATCH", "reason": "no live price — feed disconnected", "confidence": 0, "direction": "NEUTRAL", "horizon_minutes": 10, "entry_zone": [], "stop_loss": "0", "target_zone": [], "false_breakout_risk": 0, "max_holding_minutes": 120, "invalidation": "—"}
        short_out = _NoLiveFallback()
        cont_out = _NoLiveFallback()

    def cap_dict(c: Any):
        if not c:
            return {}
        return {
            "options": getattr(c, "options", False),
            "futures": getattr(c, "futures", False),
            "orderbook_l2": getattr(c, "orderbook_l2", False),
            "greeks": getattr(c, "greeks", False),
            "fii_dii": getattr(c, "fii_dii", False),
            "ai_confirmation": getattr(c, "ai_confirmation", False),
            "telegram_alerts": getattr(c, "telegram_alerts", False),
            "multi_timeframe": getattr(c, "multi_timeframe", False),
            "tick_size": float(getattr(c, "tick_size", 0.05)),
            "lot_size": getattr(c, "lot_size", 25),
            "max_leverage": getattr(c, "max_leverage", 1),
        }

    return {
        "instrument": {
            **prof.to_dict(),
            "id": prof.instrument_id,
            "symbol": getattr(prof, "symbol", prof.instrument_id),
            "name": getattr(prof, "name", prof.display_name),
            "capabilities": cap_dict(getattr(prof, "capabilities", None)),
            "contract_spec": prof.contract_spec.to_dict() if prof.contract_spec else None,
        },
        "session": {
            "is_open": clk_info.get("is_open", False),
            "session_type": clk_info.get("session_state", "CLOSED"),
            "time_to_close_seconds": None,
            "time_to_open_seconds": None,
            "clock_divergence_ms": 0,
            "is_synchronized": True,
        },
        "feed_health": {
            "health": getattr(feed_snap, "health", "HEALTHY") if spot is not None else "STALE",
            "error_count_last_min": 0,
            "consecutive_timeouts": 0,
            "circuit_state": "TRIPPED" if getattr(feed_snap, "suppress_candidates", False) else "CLOSED",
            "staleness_ms": now_ms - last_update_ms if spot is not None else 999999,
            "is_stale": True if spot is None else (now_ms - last_update_ms) > 5000,
            "used_synthetic_fallback": used_synthetic,
            "is_synthetic_fallback": is_synthetic_fallback,
        },
        "sequence": {
            "last_seq": getattr(seq_val, "_last_source_seq", None) or getattr(seq_val, "_internal_seq", 0),
            "gap_detected": getattr(seq_val, "_gap_detected", False),
            "gap_count": 0,
            "out_of_order_count": 0,
        },
        "market_intelligence": {
            "regime": ctx.technical.get("regime", "NEUTRAL"),
            "price_action": ctx.price_action,
            "bullish_score": ctx.scores.get("bullish_score", 50),
            "bearish_score": ctx.scores.get("bearish_score", 50),
            "breakout_pressure": ctx.scores.get("breakout_pressure", 50),
            "false_breakout_risk": ctx.scores.get("false_breakout_risk", 20),
            "cross_market": ctx.cross_market,
            "synchronization_status": ctx.synchronization_status,
            "spot_price": float(spot) if spot else None,
            "last_update_ms": last_update_ms,
        },
        "breakout_candidate": {
            "candidate": getattr(sig, "status", "WATCH"),
            "status": getattr(sig, "status", "WATCH"),
            "direction": getattr(sig, "direction", "BULLISH"),
            "confidence": getattr(sig, "confidence", 50),
            "trigger_level": float(sig.breakout_level) if getattr(sig, "breakout_level", None) else None,
            "reasons": [getattr(sig, "reason", "")] if getattr(sig, "reason", None) else getattr(sig, "supporting", []),
        },
        "short_horizon": short_out.to_dict(),
        "continuation": cont_out.to_dict(),
        "generated_at_ms": now_ms,
    }

