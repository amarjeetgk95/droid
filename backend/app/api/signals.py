"""
Unified Signals Facade — dedicated Signal Generation module.

Wraps institutional SignalCenter + algo signal_fusion behind a single
authoritative API. Every generated signal can fan out to Telegram via
the existing downstream pipeline (never blocks creation, §35).

Endpoints:
  POST /api/v1/signals/generate
  GET  /api/v1/signals/active   (alias to institutional active)
  GET  /api/v1/signals/history
  GET  /api/v1/signals/{signal_id}
  GET  /api/v1/signals/engines
  POST /api/v1/signals/{signal_id}/cas-execution
  POST /api/v1/telegram/dev/preview already exists for preview
"""
from __future__ import annotations

import time
import uuid
from typing import Literal, Any, Optional

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field

from app.institutional.signal import signal_fsm, create_signal
from app.institutional.signal_center import signal_center
from app.institutional.instrument_registry import asset_registry
from app.institutional.audit import audit_trail

import structlog

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])

# ── Models ──────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    instrument_id: str = Field(description="NIFTY / BANKNIFTY / SENSEX / BTCUSD")
    candle_timeframe: str = Field(default="5M", description="1M | 5M §13")
    strategy: str = Field(default="BREAKOUT", description="BREAKOUT etc")
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"] | None = None
    engine: Literal["institutional", "algo"] = Field(default="institutional")
    trigger_level: float | str | None = None
    current_price: float | str | None = None
    confidence: float | None = None  # 0-100
    breakout_pressure: int | None = None
    false_breakout_risk: float | None = None
    short_horizon: dict[str, Any] | None = None
    continuation: dict[str, Any] | None = None
    ai: dict[str, Any] | None = None
    ttl_ms: int = Field(default=5000, ge=1000, le=60000)
    status: str | None = Field(default=None, description="Override status: CONFIRMED / TRIGGERED / POSSIBLE_BREAKOUT etc")
    # Signal generation payload for algo engine
    technical: dict[str, Any] | None = None
    mtf: dict[str, Any] | None = None
    fno: dict[str, Any] | None = None
    regime: dict[str, Any] | None = None
    event_risk: dict[str, Any] | None = None
    weights: dict[str, Any] | None = None
    # Telegram
    notify_telegram: bool = Field(default=True, description="Enqueue Telegram notification after generation")
    setup_type: str | None = Field(default=None, description="BREAKOUT | BREAKDOWN — auto-derived from direction if omitted")


class PreviewRequest(BaseModel):
    instrument_id: str
    candle_timeframe: str = "5M"
    direction: str = "BULLISH"
    status: str = "CONFIRMED"
    setup_type: str | None = None
    trigger_level: float | None = None
    current_price: float | None = None
    confidence: float | None = 75
    breakout_pressure: int | None = 70
    stop_loss: float | None = None


# ── Engine capability map ─────────────────────────────────────────

def _engines() -> list[dict]:
    return [
        {
            "id": "institutional",
            "label": "Institutional Breakout",
            "description": "MarketContext + Breakout + Options + Feed-circuit aware. TTL 5s, throttled Telegram.",
            "supports": ["NIFTY", "BANKNIFTY", "SENSEX", "BTCUSD"],
            "timeframes": ["1M", "5M"],
            "ttl_ms_default": 5000,
        },
        {
            "id": "algo",
            "label": "Algo Fusion",
            "description": "Weighted fusion technical/mtf/fno/regime/ai/event_risk. Configurable weights §26.",
            "supports": ["NIFTY", "BANKNIFTY", "SENSEX", "BTCUSD"],
            "timeframes": ["1M", "5M"],
            "ttl_ms_default": 5000,
        },
    ]


@router.get("/engines")
def list_engines():
    return {"engines": _engines()}


# ── Active / history aliases ──────────────────────────────────────

@router.get("/active")
async def list_active(
    instrument: str | None = Query(None, description="Filter by NIFTY/BANKNIFTY/SENSEX/BTCUSD"),
    status: str | None = Query(None, description="Filter by CONFIRMED/WATCH/POSSIBLE_BREAKOUT etc"),
    engine: str | None = Query(None, description="institutional|algo — currently all go via institutional center"),
):
    # For now delegate to institutional center (single authoritative writer).
    # Algo fused signals are created via generate with engine=algo and also appear here.
    data = await signal_center.active_setups(instrument=instrument, status=status)
    # Tag engine for frontend filtering
    for d in data:
        d.setdefault("engine", "institutional")
    if engine:
        data = [d for d in data if d.get("engine") == engine]
    return {"signals": data, "count": len(data), "generated_at_ms": int(time.time() * 1000)}


@router.get("/history")
async def list_history(limit: int = Query(20, ge=1, le=200)):
    return {"records": audit_trail.recent(limit)}


@router.get("/{signal_id}")
def get_signal(signal_id: str):
    sig = signal_fsm.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="signal not found")
    return {
        **sig.to_dict(),
        "is_expired": sig.is_expired(),
        "ttl_remaining_ms": sig.ttl_remaining_ms(),
        "state_history": sig.state_history,
    }


@router.post("/{signal_id}/cas-execution")
def cas_execution(signal_id: str):
    ok, err = signal_fsm.cas_to_execution_pending(signal_id)
    if not ok:
        raise HTTPException(status_code=400, detail=err or "CAS failed")
    sig = signal_fsm.get(signal_id)
    return {"status": "EXECUTION_PENDING", "signal": sig.to_dict() if sig else None}


# ── Preview (render without enqueue) ──────────────────────────────

@router.post("/preview")
def preview_signal(req: PreviewRequest):
    from app.institutional.telegram_templates import render_event_message
    from app.institutional.telegram_notifications import SignalEvent

    setup = (req.setup_type or ("BREAKDOWN" if req.direction.upper() == "BEARISH" else "BREAKOUT")).upper()
    et_map = {
        "CONFIRMED": "SIGNAL_CONFIRMED",
        "TRIGGERED": "SIGNAL_TRIGGERED",
        "POSSIBLE_BREAKOUT": "POSSIBLE_SETUP",
        "POSSIBLE_BREAKDOWN": "POSSIBLE_SETUP",
        "WATCH": "POSSIBLE_SETUP",
    }
    event_type = et_map.get(req.status.upper(), "SIGNAL_CONFIRMED")
    ev = SignalEvent(
        event_type=event_type,
        signal_id=f"preview-{uuid.uuid4().hex[:8]}",
        instrument=req.instrument_id.upper(),
        candle_timeframe=req.candle_timeframe.upper(),
        setup_type=setup,
        direction=req.direction.upper(),
        status=req.status.upper(),
        trigger_level=req.trigger_level,
        current_price=req.current_price,
        stop_loss=req.stop_loss,
        confidence=req.confidence,
        breakout_pressure=req.breakout_pressure,
    )
    text = render_event_message(ev)
    return {"event_type": ev.event_type, "instrument": ev.instrument, "preview": text, "event": ev.model_dump()}


# ── Generate ──────────────────────────────────────────────────────

@router.post("/generate")
async def generate_signal(req: GenerateRequest):
    """
    Unified generation endpoint.
    - engine=institutional: creates authoritative Signal via signal.py and publishes SignalEvent to Telegram (downstream, never blocks).
    - engine=algo: delegates to algo signal_fusion for LONG/SHORT/NO_TRADE then also creates institutional Signal wrapper for Telegram compat.
    """
    iid = req.instrument_id.upper()
    prof = asset_registry.get(iid)
    if not prof:
        raise HTTPException(status_code=404, detail=f"instrument {iid} not found")
    if req.candle_timeframe.upper() not in ("1M", "5M"):
        raise HTTPException(status_code=400, detail="candle_timeframe must be 1M or 5M")
    if iid not in ("NIFTY", "BANKNIFTY", "SENSEX", "BTCUSD"):
        raise HTTPException(status_code=400, detail="instrument must be NIFTY/BANKNIFTY/SENSEX/BTCUSD")

    direction = (req.direction or "BULLISH").upper()
    if direction not in ("BULLISH", "BEARISH", "NEUTRAL"):
        raise HTTPException(status_code=400, detail="direction must be BULLISH/BEARISH/NEUTRAL")

    # Derive status/type
    status = (req.status or ("CONFIRMED" if direction in ("BULLISH", "BEARISH") else "NO_SETUP")).upper()
    setup_type = (req.setup_type or ("BREAKDOWN" if direction == "BEARISH" else "BREAKOUT")).upper()
    ttl_ms = req.ttl_ms

    # ── Resolve current_price for payload if not provided: try buffer
    current_price = req.current_price
    if current_price is None:
        try:
            from app.institutional.snapshot_buffer import synchronized_buffer
            latest = synchronized_buffer.get_latest(iid)
            if latest and latest.event.price:
                current_price = float(latest.event.price)
        except Exception:
            pass

    # ── Build Signal via signal.py (authoritative, same as signal_center) ──
    # For algo engine, run fusion first to get LONG/SHORT -> map to BULLISH/BEARISH
    algo_fusion_result: dict | None = None
    if req.engine == "algo":
        try:
            from app.algo.signal_fusion import signal_fusion, SignalInputs
            inputs = SignalInputs(
                technical=req.technical or {},
                mtf=req.mtf or {},
                fno=req.fno or {},
                regime=req.regime or {},
                ai=req.ai or {},
                event_risk=req.event_risk or {},
                weights=req.weights or {},
            )
            fused = signal_fusion.fuse(inputs, strategy_id=req.strategy, symbol=iid, instrument_id=iid)
            # Map LONG/SHORT/NO_TRADE -> BULLISH/BEARISH/NEUTRAL
            if fused.direction == "LONG":
                direction = "BULLISH"
            elif fused.direction == "SHORT":
                direction = "BEARISH"
            else:
                direction = "NEUTRAL"
                status = "NO_SETUP"
            algo_fusion_result = {
                "signal_id": str(fused.signal_id),
                "direction": fused.direction,
                "score": str(fused.score),
                "confidence": str(fused.confidence),
            }
            setup_type = "BREAKOUT" if direction == "BULLISH" else ("BREAKDOWN" if direction == "BEARISH" else "BREAKOUT")
        except Exception as e:
            logger.warning("algo_fusion_failed", error=str(e))
            # Fall through to institutional defaults

    # Feed-degraded gate: cannot generate when feed degraded? For manual generate we allow but mark Risk REJECTED downstream.
    # The engine should still create signal; Telegram will be filtered by data_health check inside SignalEvent consumption.
    signal_obj = create_signal(
        instrument_id=iid,
        strategy=req.strategy,
        direction=direction,  # type: ignore
        market_context_id=str(int(time.time() * 1000)),
        short_horizon=req.short_horizon or {"status": status, "confidence": req.confidence or 75, "horizon_minutes": 10},
        continuation=req.continuation or {"status": "WATCH", "confidence": 60},
        ai=req.ai or {"status": "UNAVAILABLE"},
        ttl_ms=ttl_ms,
    )
    signal_fsm.register(signal_obj)
    # Mark validated so it can be queried; mirrors signal_center behaviour
    try:
        signal_fsm.transition(signal_obj.signal_id, "VALIDATED")
    except Exception:
        pass

    # Audit — same as signal_center
    try:
        from app.institutional.audit import AuditRecord
        rec = AuditRecord(
            signal_id=signal_obj.signal_id,
            instrument_id=iid,
            canonical_timestamp_utc=signal_obj.created_at_utc,
            market_context={"engine": req.engine, "strategy": req.strategy, "direction": direction},
            strategy_output={"generate_request": req.model_dump(), "algo_fusion": algo_fusion_result},
            ttl_ms=ttl_ms,
            expires_at_utc=signal_obj.expires_at_utc,
            final_state=status,
        )
        audit_trail.append(rec)
    except Exception as e:
        logger.warning("signals_audit_append_failed", error=str(e))

    # ── Telegram fan-out (downstream, never blocks creation, §35) ──
    telegram_result: dict[str, Any] = {"enqueued": 0, "notification_ids": [], "skipped_reason": None}
    if req.notify_telegram and status != "NO_SETUP":
        try:
            from app.institutional.telegram_notifications import SignalEvent, should_publish_instrument_event, telegram_notification_queue
            # Map status -> event_type
            event_type_map = {
                "TRIGGERED": "SIGNAL_TRIGGERED",
                "CONFIRMED": "SIGNAL_CONFIRMED",
                "POSSIBLE_BREAKOUT": "POSSIBLE_SETUP",
                "POSSIBLE_BREAKDOWN": "POSSIBLE_SETUP",
                "WATCH": "POSSIBLE_SETUP",
                "EXPIRED": "SIGNAL_EXPIRED",
                "INVALIDATED": "SIGNAL_INVALIDATED",
            }
            ev_type = event_type_map.get(status, "SIGNAL_CONFIRMED")
            # Throttle per (instrument, event_type) 60s
            if not should_publish_instrument_event(iid, ev_type, min_interval_s=60.0):
                telegram_result["skipped_reason"] = f"throttled {iid}:{ev_type} within 60s"
            else:
                # Derive payload
                trig_lv = None
                try:
                    trig_lv = float(req.trigger_level) if req.trigger_level is not None else (float(current_price) * 1.005 if current_price else None)  # type: ignore
                except Exception:
                    trig_lv = None
                stop_lv = None
                try:
                    if iid == "BTCUSD":
                        ctf = req.candle_timeframe.upper()
                        # no-op
                        pass
                    # try to pull stop from short_horizon
                    sh = req.short_horizon or {}
                    if isinstance(sh.get("stop_loss"), (int, float, str)):
                        stop_lv = float(sh["stop_loss"])  # type: ignore
                except Exception:
                    stop_lv = None
                ev = SignalEvent(
                    event_type=ev_type,
                    signal_id=signal_obj.signal_id,
                    instrument=iid,
                    candle_timeframe=req.candle_timeframe.upper(),
                    setup_type=setup_type,
                    direction=direction,
                    status=status,
                    trigger_level=trig_lv,
                    current_price=float(current_price) if current_price is not None else None,  # type: ignore
                    stop_loss=stop_lv,
                    confidence=float(req.confidence) if req.confidence is not None else None,
                    breakout_pressure=req.breakout_pressure,
                    false_breakout_risk=req.false_breakout_risk,
                    ai_status=(signal_obj.ai or {}).get("status") if isinstance(signal_obj.ai, dict) else None,
                )
                ids = await telegram_notification_queue.publish_signal_event(ev)
                telegram_result["enqueued"] = len(ids)
                telegram_result["notification_ids"] = ids
                if not ids:
                    # May be SKIPPED due to prefs or dedup — surface audit hint
                    telegram_result["skipped_reason"] = "no eligible Telegram bindings or filtered by preferences/dedup"
        except Exception as e:  # §35 — never propagate
            logger.warning("signals_telegram_publish_failed", error=str(e))
            telegram_result["skipped_reason"] = str(e)
    elif status == "NO_SETUP":
        telegram_result["skipped_reason"] = "NO_SETUP not notified"

    # Build unified signal DTO for frontend (mirrors signal_center active shape)
    trigger_fmt = None
    try:
        if req.trigger_level is not None:
            trigger_fmt = format(float(req.trigger_level), 'f')
        elif current_price is not None:
            trigger_fmt = format(float(current_price) * 1.005, 'f')  # type: ignore
    except Exception:
        trigger_fmt = None

    price_fmt = None
    if current_price is not None:
        try:
            price_fmt = f"{float(current_price):,.2f}"  # type: ignore
        except Exception:
            price_fmt = str(current_price)

    dto = {
        "signal_id": signal_obj.signal_id,
        "instrument_id": iid,
        "display_name": prof.display_name if prof else iid,
        "engine": req.engine,
        "strategy": req.strategy,
        "status": status,
        "direction": direction,
        "setup_type": setup_type,
        "candle_timeframe": req.candle_timeframe.upper(),
        "trigger_level": trigger_fmt,
        "price": str(current_price) if current_price is not None else None,
        "price_formatted": price_fmt,
        "confidence": req.confidence,
        "breakout_pressure": req.breakout_pressure,
        "false_breakout_risk": req.false_breakout_risk,
        "ttl_ms": ttl_ms,
        "created_at_utc": signal_obj.created_at_utc,
        "expires_at_utc": signal_obj.expires_at_utc,
        "fsm_state": signal_obj.fsm_state,
        "short_horizon": signal_obj.short_horizon,
        "continuation": signal_obj.continuation,
        "algo_fusion": algo_fusion_result,
        "backend_authoritative": True,
    }

    return {
        "signal": dto,
        "signal_obj": signal_obj.to_dict(),
        "telegram": telegram_result,
        "is_expired": signal_obj.is_expired(),
        "ttl_remaining_ms": signal_obj.ttl_remaining_ms(),
    }
