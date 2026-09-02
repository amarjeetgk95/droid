"""
Unified Signal Centre API Router
Institutional-Grade Endpoints for Indian Index Options (NIFTY, BANKNIFTY, SENSEX) on FYERS.
"""
from __future__ import annotations

import time
import uuid
from decimal import Decimal
from typing import Literal, Any, Optional

from fastapi import APIRouter, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import structlog

from app.signals.contract_resolver import (
    APPROVED_UNDERLYINGS,
    validate_underlying,
    resolve_option_contract,
    calculate_position_sizing,
    normalize_price,
)
from app.signals.strategies import STRATEGY_REGISTRY
from app.signals.strategies.base import StrategyContext, SignalCandidate
from app.signals.confluence import confluence_engine
from app.signals.fsm import signal_fsm, SignalInstance
from app.signals.scanner import scanner_engine
from app.signals.outcome_tracker import outcome_tracker
from app.signals.paper_engine import signal_paper_engine
from app.signals.sse import signal_sse_hub
from app.services.market_service import MarketService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


# ── Request / Response Models ──────────────────────────────────────────

class GenerateSignalRequest(BaseModel):
    underlying: str = Field(description="NIFTY / BANKNIFTY / SENSEX")
    strategy: Literal["BREAKOUT", "MEAN_REVERSION", "TREND_PULLBACK", "GAMMA_SQUEEZE", "ORB"] = "BREAKOUT"
    direction: Literal["LONG_CALL", "LONG_PUT"] = "LONG_CALL"
    timeframe: Literal["1M", "5M", "15M", "1H", "1D"] = "5M"
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    trigger: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    confidence: Optional[float] = 80.0
    execute_paper: bool = Field(default=False, description="Auto-execute paper order")
    lots: Optional[int] = Field(default=None, description="Optional custom lots")
    notify_telegram: bool = Field(default=True, description="Enqueue Telegram notification")
    rationale: Optional[list[str]] = None


class AutoDetectRequest(BaseModel):
    underlying: str
    strategy: str = "BREAKOUT"
    timeframe: str = "5M"


class ExecutePaperRequest(BaseModel):
    lots: Optional[int] = Field(default=None, description="Optional custom lots override")
    risk_percent: float = Field(default=2.0, description="Risk capital % for sizing")


# ── 1. ACTIVE SIGNALS LIST ───────────────────────────────────────────

@router.get("/active")
async def list_active_signals(
    instrument: Optional[str] = Query(None, description="Filter by NIFTY / BANKNIFTY / SENSEX"),
    strategy: Optional[str] = Query(None, description="Filter by BREAKOUT / MEAN_REVERSION / etc"),
    status: Optional[str] = Query(None, description="Filter by FSM state"),
):
    """
    Returns active signals with live price distance, contract specs, and R:R metrics.
    """
    signals = signal_fsm.list_active(underlying=instrument, strategy=strategy)
    
    # Update outcomes with latest prices
    market_svc = MarketService()
    dto_list = []
    
    for s in signals:
        if status and status != "ALL" and s.fsm_state != status:
            continue
            
        # Compute live distance to trigger
        distance_pts = None
        distance_pct = None
        try:
            quote = await market_svc.get_quote(s.underlying)
            if quote and quote.ltp is not None:
                curr_p = Decimal(str(quote.ltp))
                # Check outcome progression
                outcome_tracker.update_with_price(s.underlying, curr_p)
                
                diff = abs(curr_p - s.trigger)
                distance_pts = float(diff.quantize(Decimal("0.05")))
                distance_pct = float((diff / s.trigger * Decimal("100")).quantize(Decimal("0.01"))) if s.trigger > 0 else 0.0
        except Exception:
            pass

        d = s.model_dump()
        d["distance_to_trigger_pts"] = distance_pts
        d["distance_to_trigger_pct"] = distance_pct
        d["ttl_remaining_seconds"] = s.ttl_remaining_seconds()
        dto_list.append(d)

    return {
        "signals": dto_list,
        "count": len(dto_list),
        "timestamp_ms": int(time.time() * 1000),
    }


# ── 2. REAL-TIME MULTI-STRATEGY SCANNER ───────────────────────────────

@router.get("/scanner")
async def run_scanner():
    """
    Scans NIFTY, BANKNIFTY, SENSEX across all 5 quant strategies simultaneously.
    """
    scan_result = await scanner_engine.scan_all()
    # Broadcast P2 scan event via SSE
    await signal_sse_hub.broadcast("scanner_update", {"total_signals": len(scan_result.get("active_signals", []))}, priority="P2")
    return scan_result


# ── 3. PERFORMANCE ATTRIBUTION & ANALYTICS ────────────────────────────

@router.get("/performance")
def get_performance_stats():
    """
    Returns Win Rate %, Profit Factor, Expectancy, and Strategy breakdown.
    """
    return outcome_tracker.get_performance_metrics().model_dump()


# ── 4. SIGNAL DEEP-DIVE TECHNICAL BREAKDOWN ───────────────────────────

@router.get("/{signal_id}/deep-dive")
async def get_signal_deep_dive(signal_id: str):
    """
    Comprehensive technical dossier for a single signal.
    """
    sig = signal_fsm.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")

    market_svc = MarketService()
    quote = await market_svc.get_quote(sig.underlying)
    curr_price = float(quote.ltp) if quote and quote.ltp else float(sig.spot_price)

    # Calculate recommended sizing for standard ₹1,00,000 / ₹5,00,000 account
    opt = sig.option_contract or {}
    lot_size = int(opt.get("lot_size", 75))
    sizing_1l = calculate_position_sizing(100000.0, 2.0, sig.spot_price, sig.stop_loss, lot_size)
    sizing_5l = calculate_position_sizing(500000.0, 2.0, sig.spot_price, sig.stop_loss, lot_size)

    return {
        "signal": sig.model_dump(),
        "current_market_price": curr_price,
        "confluence": sig.confluence_breakdown,
        "option_contract": sig.option_contract,
        "fsm_history": [h.model_dump() for h in sig.state_history],
        "position_sizing_preview": {
            "account_1lakh": sizing_1l,
            "account_5lakh": sizing_5l,
        },
        "levels": {
            "entry_range": [float(sig.entry_min), float(sig.entry_max)],
            "trigger": float(sig.trigger),
            "stop_loss": float(sig.stop_loss),
            "target_1": float(sig.target_1),
            "target_2": float(sig.target_2),
            "risk_points": float(sig.risk_points),
            "risk_reward_t1": sig.risk_reward_t1,
            "risk_reward_t2": sig.risk_reward_t2,
        },
        "timestamp_ms": int(time.time() * 1000),
    }


# ── 5. SINGLE SIGNAL QUERY ────────────────────────────────────────────

@router.get("/{signal_id}")
def get_signal_by_id(signal_id: str):
    sig = signal_fsm.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig.model_dump()


# ── 6. 1-CLICK PAPER TRADING EXECUTION ────────────────────────────────

@router.post("/{signal_id}/execute-paper")
async def execute_signal_paper(signal_id: str, req: Optional[ExecutePaperRequest] = None):
    """
    1-Click manual execution of any active signal into the Paper Trading Engine.
    """
    try:
        lots = req.lots if req else None
        risk_pct = req.risk_percent if req else 2.0
        result = await signal_paper_engine.execute_signal(
            signal_id=signal_id,
            lots_override=lots,
            risk_percent=risk_pct,
        )
        # Broadcast P0 execution event
        await signal_sse_hub.broadcast("paper_execution", result.model_dump(), priority="P0")
        return result.model_dump()
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error("paper_execution_failed", signal_id=signal_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Paper execution failed: {str(e)}")


# ── 7. AUTO-DETECT LIVE SETUP (PRE-FILL GENERATOR) ────────────────────

@router.post("/auto-detect")
async def auto_detect_setup(req: AutoDetectRequest):
    """
    Evaluates live candles and indicators to automatically pre-fill realistic Entry, SL, and Target levels.
    """
    try:
        candidates = await scanner_engine.scan_instrument(req.underlying, timeframe=req.timeframe)
        # Filter for requested strategy if available
        matched = [c for c in candidates if c.strategy == req.strategy.upper()]
        selected = matched[0] if matched else (candidates[0] if candidates else None)

        if selected:
            return {
                "detected": True,
                "candidate": selected.model_dump(),
                "message": f"Detected {selected.strategy} {selected.direction} on {req.underlying}",
            }
        
        # Fallback to current price baseline if no active breakout
        market_svc = MarketService()
        quote = await market_svc.get_quote(req.underlying)
        spot = Decimal(str(quote.ltp if quote and quote.ltp else 24800.0))
        tick = Decimal("0.05")
        contract = resolve_option_contract(req.underlying, spot, "CE", strike_offset=0)

        entry = normalize_price(spot, tick)
        sl = normalize_price(spot * Decimal("0.995"), tick)
        t1 = normalize_price(spot + ((entry - sl) * Decimal("1.5")), tick)
        t2 = normalize_price(spot + ((entry - sl) * Decimal("3.0")), tick)

        return {
            "detected": False,
            "candidate": {
                "underlying": req.underlying,
                "strategy": req.strategy,
                "direction": "LONG_CALL",
                "timeframe": req.timeframe,
                "spot_price": float(spot),
                "entry_min": float(entry),
                "entry_max": float(entry + Decimal("10.0")),
                "trigger": float(entry + tick),
                "stop_loss": float(sl),
                "target_1": float(t1),
                "target_2": float(t2),
                "confidence": 75.0,
                "option_contract": contract.model_dump(),
            },
            "message": "No active setup triggered; populated baseline levels from spot price.",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 8. MANUAL SIGNAL GENERATION ───────────────────────────────────────

@router.post("/generate")
async def generate_signal(req: GenerateSignalRequest):
    """
    Manual authoritative signal generation with FSM registration, optional paper execution, and Telegram dispatch.
    """
    u = validate_underlying(req.underlying)
    market_svc = MarketService()
    quote = await market_svc.get_quote(u)
    spot = Decimal(str(quote.ltp if quote and quote.ltp else (req.trigger or 24800.0)))
    tick = Decimal("0.05")

    entry_min = normalize_price(req.entry_min or spot, tick)
    entry_max = normalize_price(req.entry_max or (spot + Decimal("10.0")), tick)
    trigger = normalize_price(req.trigger or (entry_min + tick), tick)
    stop_loss = normalize_price(req.stop_loss or (spot * Decimal("0.995")), tick)
    
    risk_pts = abs(entry_min - stop_loss)
    t1 = normalize_price(req.target_1 or (entry_min + (risk_pts * Decimal("1.5"))), tick)
    t2 = normalize_price(req.target_2 or (entry_min + (risk_pts * Decimal("3.0"))), tick)

    opt_type = "CE" if "CALL" in req.direction else "PE"
    contract = resolve_option_contract(u, spot, opt_type, strike_offset=0)

    instance = SignalInstance(
        underlying=u,
        strategy=req.strategy,
        direction=req.direction,
        timeframe=req.timeframe,
        spot_price=spot,
        entry_min=entry_min,
        entry_max=entry_max,
        trigger=trigger,
        stop_loss=stop_loss,
        target_1=t1,
        target_2=t2,
        risk_points=risk_pts,
        risk_reward_t1=float(((t1 - entry_min) / risk_pts).quantize(Decimal("0.1"))) if risk_pts > 0 else 1.5,
        risk_reward_t2=float(((t2 - entry_min) / risk_pts).quantize(Decimal("0.1"))) if risk_pts > 0 else 3.0,
        confidence=req.confidence or 80.0,
        confluence_breakdown={"technical": 80.0, "mtf": 75.0, "fno": 75.0, "regime": 80.0, "ai": 75.0},
        rationale=req.rationale or [f"Manual {req.strategy} setup on {u}"],
        option_contract=contract.model_dump(),
        fsm_state="CONFIRMED" if req.execute_paper else "ARMED",
    )
    signal_fsm.register(instance)

    paper_result = None
    if req.execute_paper:
        try:
            paper_result = await signal_paper_engine.execute_signal(instance.signal_id, lots_override=req.lots)
        except Exception as pe:
            logger.warning("generate_signal_paper_auto_failed", error=str(pe))

    # Optional Telegram Notification
    telegram_res = {"enqueued": 0}
    if req.notify_telegram:
        try:
            from app.institutional.telegram_notifications import SignalEvent, telegram_notification_queue
            ev = SignalEvent(
                event_type="SIGNAL_CONFIRMED",
                signal_id=instance.signal_id,
                instrument=u,
                candle_timeframe=req.timeframe,
                setup_type=req.strategy,
                direction="BULLISH" if "CALL" in req.direction else "BEARISH",
                status=instance.fsm_state,
                trigger_level=float(instance.trigger),
                current_price=float(instance.spot_price),
                stop_loss=float(instance.stop_loss),
                confidence=float(instance.confidence),
            )
            ids = await telegram_notification_queue.publish_signal_event(ev)
            telegram_res["enqueued"] = len(ids)
        except Exception as te:
            logger.warning("generate_telegram_dispatch_failed", error=str(te))

    # Broadcast P0 Signal Creation via SSE
    await signal_sse_hub.broadcast("signal_created", instance.model_dump(), priority="P0")

    return {
        "success": True,
        "signal": instance.model_dump(),
        "paper_order": paper_result.model_dump() if paper_result else None,
        "telegram": telegram_res,
    }


# ── 9. REAL-TIME SERVER-SENT EVENTS (SSE) STREAM ──────────────────────

@router.get("/stream")
async def stream_signals(request: Request):
    """
    Live low-latency SSE feed for real-time signal creation, FSM transitions, and execution receipts.
    """
    q = signal_sse_hub.subscribe()
    return StreamingResponse(
        signal_sse_hub.event_generator(q),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 10. ENGINES & STRATEGY CATALOG ────────────────────────────────────

@router.get("/engines")
def list_strategy_engines():
    return {
        "approved_universe": list(APPROVED_UNDERLYINGS),
        "broker": "FYERS API v3",
        "strategies": [
            {"id": "BREAKOUT", "label": "Institutional Breakout", "description": "S/R violation with volume expansion (>1.4x) and pressure confirmation."},
            {"id": "MEAN_REVERSION", "label": "Mean Reversion", "description": "2.0σ Bollinger Band & RSI oversold/overbought exhaustion in range regime."},
            {"id": "TREND_PULLBACK", "label": "Trend Pullback", "description": "EMA 20/50/200 ribbon alignment with low-volume pullback retests."},
            {"id": "GAMMA_SQUEEZE", "label": "Gamma Squeeze", "description": "ATM Call/Put OI unwinding with PCR extremes and Delta acceleration."},
            {"id": "ORB", "label": "Opening Range Breakout (15M)", "description": "First 15-minute high/low breakout with session momentum confirmation."},
        ],
    }
