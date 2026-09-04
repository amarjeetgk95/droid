"""
Unified Signal Centre API Router
Institutional-Grade Endpoints for Indian Index Options (NIFTY, BANKNIFTY, SENSEX) on FYERS.
"""
from __future__ import annotations

import time
import uuid
import asyncio
from decimal import Decimal
from typing import Literal, Any, Optional

from fastapi import APIRouter, Query, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.core.security import get_current_user, AuthUser
from app.core.database import get_db_session

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
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.scanner import scanner_engine
from app.signals.outcome_tracker import outcome_tracker
from app.signals.paper_engine import signal_paper_engine
from app.signals.sse import signal_sse_hub
from app.services.market_service import MarketService

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])


# ── Request / Response Models ──────────────────────────────────────────

class GenerateSignalRequest(BaseModel):
    underlying: Optional[str] = Field(default=None, description="NIFTY / BANKNIFTY / SENSEX")
    instrument_id: Optional[str] = Field(default=None, description="Compatibility alias for underlying")
    strategy: str = "BREAKOUT"
    direction: str = "LONG_CALL"
    timeframe: Optional[str] = Field(default=None, description="1M, 3M, 5M, 15M, 1H, 1D")
    candle_timeframe: Optional[str] = Field(default=None, description="Compatibility alias for timeframe")
    status: Optional[str] = None
    signal_type: Optional[str] = Field(default="INTRADAY", description="SCALP or INTRADAY")
    is_scalp: bool = Field(default=False, description="Flag indicating high-frequency scalp setup")
    time_stop_seconds: Optional[int] = None
    runner_ttl_seconds: Optional[int] = None
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    trigger: Optional[float] = None
    trigger_level: Optional[float] = None
    current_price: Optional[float] = None
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
    quantity: Optional[int] = Field(default=None, description="Optional custom quantity override")
    risk_percent: float = Field(default=2.0, description="Risk capital % for sizing")


class PreviewSignalRequest(BaseModel):
    instrument_id: Optional[str] = None
    underlying: Optional[str] = None
    candle_timeframe: Optional[str] = "5M"
    timeframe: Optional[str] = None
    direction: str = "BULLISH"
    status: str = "CONFIRMED"
    trigger_level: Optional[float] = None
    trigger: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    confidence: Optional[float] = None
    setup_type: Optional[str] = "BREAKOUT"
    strategy: Optional[str] = None


class PaperWalletCapitalRequest(BaseModel):
    capital: float


# ── 1. ACTIVE SIGNALS LIST ───────────────────────────────────────────

VALID_INSTRUMENTS = {"NIFTY", "BANKNIFTY", "SENSEX"}
VALID_DESKS = {"SCALP", "INTRADAY", "ALL"}


def _quote_is_fallback(quote: Any) -> bool:
    try:
        status = str(getattr(quote, "status", "") or "").upper()
        provider = str(getattr(quote, "provider", "") or "").lower()
        return "OFFLINE" in status or provider in ("fallback", "synthetic", "mock")
    except Exception:
        return False


@router.get("/active")
async def list_active_signals(
    instrument: Optional[str] = Query(None, description="Filter by NIFTY / BANKNIFTY / SENSEX"),
    strategy: Optional[str] = Query(None, description="Filter by strategy name"),
    status: Optional[str] = Query(None, description="Filter by FSM state"),
    desk: Optional[str] = Query(None, description="Filter by desk: SCALP, INTRADAY, or ALL"),
    is_scalp: Optional[bool] = Query(None, description="Filter specifically for scalp signals"),
):
    """
    Returns active signals with live price distance, contract specs, R:R metrics, and desk categorization.
    Never fails hard on a stale quote — per-signal quotes degrade independently (allSettled pattern).
    """
    import asyncio

    if instrument and instrument.upper() not in VALID_INSTRUMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown instrument '{instrument}'. Approved universe: {sorted(VALID_INSTRUMENTS)}",
        )
    if desk and desk.upper() not in VALID_DESKS:
        raise HTTPException(status_code=422, detail=f"Unknown desk '{desk}'. Use SCALP, INTRADAY, or ALL.")

    signals = signal_fsm.list_active(underlying=instrument, strategy=strategy)

    # Update outcomes with latest prices
    market_svc = MarketService()

    # ── Parallel quote fetch (bounded, single-flight per underlying) ──
    underlyings = sorted({s.underlying for s in signals})
    quotes: dict[str, Any] = {}
    quote_errors: dict[str, str] = {}
    degraded_underlyings: list[str] = []

    async def _fetch_quote(u: str):
        try:
            q = await asyncio.wait_for(market_svc.get_quote(u), timeout=6.0)
            if q is None or getattr(q, "ltp", None) is None or _quote_is_fallback(q):
                quote_errors[u] = f"stale_or_fallback provider={getattr(q, 'provider', '?')}"
                degraded_underlyings.append(u)
                return
            quotes[u] = q
        except asyncio.TimeoutError:
            quote_errors[u] = "quote_timeout_after_6s"
            degraded_underlyings.append(u)
        except Exception as e:
            quote_errors[u] = str(e)[:150]
            degraded_underlyings.append(u)

    if underlyings:
        await asyncio.gather(*[_fetch_quote(u) for u in underlyings])

    dto_list = []

    for s in signals:
        if status and status != "ALL" and s.fsm_state != status:
            continue
        if desk == "SCALP" and not getattr(s, "is_scalp", False):
            continue
        if desk == "INTRADAY" and getattr(s, "is_scalp", False):
            continue
        if is_scalp is not None and getattr(s, "is_scalp", False) != is_scalp:
            continue
            
        # Compute live distance to trigger (from pre-fetched quotes — no N+1)
        distance_pts = None
        distance_pct = None
        data_quality = "LIVE"
        quote = quotes.get(s.underlying)
        try:
            if quote is not None and getattr(quote, "ltp", None) is not None:
                curr_p = Decimal(str(quote.ltp))
                # Check outcome progression (best-effort, never breaks listing)
                try:
                    outcome_tracker.update_with_price(s.underlying, curr_p)
                except Exception:
                    pass

                trig = s.trigger if s.trigger and s.trigger > 0 else None
                if trig:
                    diff = abs(curr_p - trig)
                    distance_pts = float(diff.quantize(Decimal("0.05")))
                    distance_pct = float((diff / trig * Decimal("100")).quantize(Decimal("0.01")))
            else:
                data_quality = "DEGRADED" if s.underlying not in quote_errors else "OFFLINE"
        except Exception:
            data_quality = "DEGRADED"

        d = s.model_dump()
        d["distance_to_trigger_pts"] = distance_pts
        d["distance_to_trigger_pct"] = distance_pct
        d["ttl_remaining_seconds"] = s.ttl_remaining_seconds()
        d["data_quality"] = data_quality
        dto_list.append(d)

    degraded = sorted(set(degraded_underlyings))
    return {
        "signals": dto_list,
        "count": len(dto_list),
        "data_quality": "DEGRADED" if degraded else "LIVE",
        "degraded_underlyings": degraded,
        "errors": quote_errors,
        "timestamp_ms": int(time.time() * 1000),
    }


# ── 2. REAL-TIME MULTI-STRATEGY SCANNER ───────────────────────────────

@router.get("/scanner")
async def run_scanner(desk: Optional[str] = Query(None, description="SCALP, INTRADAY, or ALL")):
    """
    Scans NIFTY, BANKNIFTY, SENSEX across requested Desk or all strategies simultaneously.
    Partial failures degrade per-underlying (errors + diagnostics) instead of 500ing the whole scan.
    Results are short-TTL cached (10s) to prevent poll storms.
    """
    desk_norm = (desk or "ALL").upper()
    if desk_norm not in VALID_DESKS:
        raise HTTPException(status_code=422, detail=f"Unknown desk '{desk}'. Use SCALP, INTRADAY, or ALL.")
    try:
        if desk_norm == "SCALP":
            scan_result = await scanner_engine.scan_scalp()
        elif desk_norm == "INTRADAY":
            scan_result = await scanner_engine.scan_intraday()
        else:
            scan_result = await scanner_engine.scan_all()
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except Exception as e:
        logger.error("scanner_failed", error=str(e))
        raise HTTPException(status_code=503, detail=f"Scanner temporarily unavailable: {str(e)[:200]}")

    # Broadcast P2 scan event via SSE (best-effort — never breaks the scan)
    try:
        active_count = len(scan_result.get("active_signals", [])) if "active_signals" in scan_result else len(scan_result.get("new_signals", []))
        await signal_sse_hub.broadcast("scanner_update", {"total_signals": active_count, "desk": desk_norm}, priority="P2")
    except Exception:
        pass
    return scan_result


@router.get("/status")
async def get_signals_status():
    """Lightweight health probe for the Signal Centre (no scan, no quotes)."""
    try:
        active = signal_fsm.list_active()
        return {
            "active_count": len(active),
            "confirmed_count": sum(1 for s in active if s.fsm_state == "CONFIRMED"),
            "armed_count": sum(1 for s in active if s.fsm_state in ("ARMED", "VALIDATED", "TRIGGERED")),
            "diagnostics": scanner_engine.get_last_diagnostics(),
            "timestamp_ms": int(time.time() * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Status unavailable: {str(e)[:150]}")


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


# ── 5. SIGNAL AUDIT LEDGER & PROFIT / LOSS ───────────────────────────

@router.get("/audit")
async def get_signals_audit(
    underlying: Optional[str] = Query(None, description="Filter by NIFTY / BANKNIFTY / SENSEX"),
    strategy: Optional[str] = Query(None, description="Filter by strategy"),
    status: Optional[str] = Query(None, description="Filter by status: WON, LOST, EXECUTED, ARMED, etc."),
    limit: int = Query(100, description="Max records to return"),
):
    """
    Authoritative Signal Audit Ledger showing real trade lifecycle,
    actual fill vs trigger, current market LTP, duration, and exact realized & unrealized P&L.
    """
    from app.signals.audit_ledger import signal_audit_ledger
    from app.signals.contract_resolver import APPROVED_UNDERLYINGS

    # Sync with FSM and Paper Service
    signal_audit_ledger.sync_with_fsm()
    signal_audit_ledger.sync_with_paper_service()

    # Fetch live quotes to compute real-time MTM
    market_svc = MarketService()
    quotes: dict[str, float] = {}
    for u in APPROVED_UNDERLYINGS:
        try:
            q = await market_svc.get_quote(u)
            if q and getattr(q, "ltp", None) is not None:
                quotes[u] = float(q.ltp)
        except Exception:
            pass

    if quotes:
        signal_audit_ledger.update_live_quotes_batch(quotes)

    trades = signal_audit_ledger.list_trades(underlying=underlying, strategy=strategy, status=status, limit=limit)
    summary = signal_audit_ledger.get_summary_metrics()
    return {
        "trades": [t.model_dump() for t in trades],
        "count": len(trades),
        "summary": summary,
        "timestamp_ms": int(time.time() * 1000),
    }


@router.get("/{signal_id}/audit")
async def get_single_signal_audit(signal_id: str):
    """
    Detailed audit record for a single signal including all transition history and actual PnL.
    """
    from app.signals.audit_ledger import signal_audit_ledger
    trade = signal_audit_ledger.get(signal_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Signal audit record not found")

    if trade.status in ("ARMED", "CONFIRMED", "EXECUTED"):
        try:
            market_svc = MarketService()
            q = await market_svc.get_quote(trade.underlying)
            if q and getattr(q, "ltp", None) is not None:
                signal_audit_ledger.update_live_quote(trade.underlying, float(q.ltp))
                trade = signal_audit_ledger.get(signal_id) or trade
        except Exception:
            pass

    return trade.model_dump()


# ── 6. SIGNALS AUDIT HISTORY ──────────────────────────────────────────

@router.get("/history")
def get_signals_history(limit: int = 50):
    """Return historical signal audit trade records."""
    records = signal_audit_ledger.list_trades(limit=limit)
    return {
        "data": [r.model_dump() for r in records],
        "count": len(records),
        "records": [r.model_dump() for r in records],
    }


# ── 7. SIGNAL DELETION AUTHORITY ──────────────────────────────────────

async def _delete_signal_core(signal_id: str) -> dict:
    """Shared delete path: square off paper, drop FSM + audit + Supabase. Best-effort per store."""
    audit_rec = signal_audit_ledger.get(signal_id)
    if audit_rec and audit_rec.status in ("ARMED", "CONFIRMED", "EXECUTED"):
        try:
            await signal_paper_engine.close_signal_position(signal_id, reason="DELETED_BY_USER")
        except Exception as pe:
            logger.warning("close_position_on_delete_failed", signal_id=signal_id, error=str(pe))

    fsm_del = signal_fsm.delete(signal_id)
    audit_del = signal_audit_ledger.delete_trade(signal_id)

    try:
        from app.signals.signals_persistence import delete_persisted_signal
        await delete_persisted_signal(signal_id)
    except Exception as se:
        logger.warning("supabase_delete_failed", signal_id=signal_id, error=str(se))

    return {"signal_id": signal_id, "fsm_deleted": fsm_del, "audit_deleted": audit_del}


class BulkDeleteRequest(BaseModel):
    signal_ids: list[str] = Field(default_factory=list, description="Explicit signal IDs to delete")
    before_ms: Optional[int] = Field(default=None, description="Delete signals created before this epoch-ms (datewise clear)")
    underlying: Optional[str] = Field(default=None, description="Filter: NIFTY / BANKNIFTY / SENSEX")
    strategy: Optional[str] = Field(default=None, description="Filter by strategy name")
    status: Optional[str] = Field(default=None, description="Filter by FSM/audit status")
    delete_all: bool = Field(default=False, description="Delete everything matching the filters")
    confirm_all: bool = Field(default=False, description="Required safety flag when delete_all has no other selector")


@router.post("/bulk-delete")
async def bulk_delete_signals(req: BulkDeleteRequest):
    """
    Multi-delete + datewise clear. Selectors combine with AND:
    explicit IDs ∪ (FSM + audit records matching underlying/strategy/status/before_ms).
    delete_all=true with no other selector needs confirm_all=true. Capped at 500/call.
    """
    ids: list[str] = []
    seen: set[str] = set()

    def _add(sid: Any) -> None:
        s = str(sid or "").strip()
        if s and s not in seen:
            seen.add(s)
            ids.append(s)

    for sid in req.signal_ids or []:
        _add(sid)

    need_scan = bool(req.before_ms or req.delete_all or req.underlying or req.strategy or req.status)
    if need_scan:
        u = (req.underlying or "").upper() or None
        if u == "ALL":
            u = None
        strat = (req.strategy or "").upper() or None
        if strat == "ALL":
            strat = None
        st = (req.status or "").upper() or None
        if st == "ALL":
            st = None

        for s in signal_fsm.list_active():
            if u and s.underlying != u:
                continue
            if strat and s.strategy != strat:
                continue
            if st and s.fsm_state != st:
                continue
            if req.before_ms and not (s.created_at_utc < req.before_ms):
                continue
            _add(s.signal_id)

        for t in signal_audit_ledger.list_trades(limit=10000):
            if u and t.underlying != u:
                continue
            if strat and t.strategy != strat:
                continue
            if st and t.status != st:
                continue
            if req.before_ms and not (t.created_at_utc < req.before_ms):
                continue
            _add(t.signal_id)

    if not ids:
        raise HTTPException(status_code=400, detail="Nothing selected: pass signal_ids or a filter (before_ms/underlying/strategy/status/delete_all).")
    if req.delete_all and not req.confirm_all and not req.signal_ids and not req.before_ms:
        raise HTTPException(status_code=400, detail="Bulk delete-all needs confirm_all=true.")
    ids = ids[:500]

    deleted: list[str] = []
    for sid in ids:
        try:
            res = await _delete_signal_core(sid)
            if res["fsm_deleted"] or res["audit_deleted"]:
                deleted.append(sid)
        except Exception as e:
            logger.warning("bulk_delete_item_failed", signal_id=sid, error=str(e))

    try:
        await signal_sse_hub.broadcast(
            "signals_bulk_deleted", {"signal_ids": deleted, "count": len(deleted)}, priority="P0"
        )
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Deleted {len(deleted)} of {len(ids)} selected signals",
        "deleted_count": len(deleted),
        "deleted_ids": deleted,
        "requested_count": len(ids),
    }


@router.delete("/{signal_id}")
async def delete_signal_by_id(signal_id: str):
    """
    Authority to delete a signal: removes from FSM, Audit Ledger, Supabase,
    squares off any open paper position, and broadcasts signal_deleted event.
    """
    res = await _delete_signal_core(signal_id)

    # Broadcast SSE
    await signal_sse_hub.broadcast("signal_deleted", {"signal_id": signal_id}, priority="P0")

    return {
        "status": "success",
        "message": f"Signal {signal_id} deleted successfully",
        "fsm_deleted": res["fsm_deleted"],
        "audit_deleted": res["audit_deleted"],
    }


# ── 6. 1-CLICK PAPER TRADING EXECUTION ────────────────────────────────

@router.post("/{signal_id}/execute-paper")
async def execute_signal_paper(signal_id: str, req: Optional[ExecutePaperRequest] = None):
    """
    1-Click manual execution of any active signal into the Paper Trading Engine.
    """
    try:
        lots = req.lots if req else None
        qty = req.quantity if req else None
        risk_pct = req.risk_percent if req else 2.0
        result = await signal_paper_engine.execute_signal(
            signal_id=signal_id,
            lots_override=lots,
            quantity_override=qty,
            risk_percent=risk_pct,
        )
        sig = signal_fsm.get(signal_id)
        is_bearish = "BEARISH" in (sig.direction if sig else "") or "PUT" in (sig.direction if sig else "")
        side_val = "SELL" if is_bearish else "BUY"

        # Broadcast P0 execution event
        await signal_sse_hub.broadcast("paper_execution", result.model_dump(), priority="P0")
        res_data = result.model_dump()
        res_data["paper_order"] = {
            "order_id": result.order_id,
            "status": result.status,
            "side": side_val,
            "quantity": result.quantity,
            "underlying": result.underlying,
            "fill_price": result.fill_price,
        }
        return res_data
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
    Returns detected=False with baseline levels when no setup triggers (never 500s on empty).
    """
    try:
        u = validate_underlying(req.underlying)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    try:
        candidates = await scanner_engine.scan_instrument(u, timeframe=req.timeframe)
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
    Rejects unknown underlyings (422) and incoherent levels (400); never fabricates fills off fallback quotes.
    """
    raw_u = req.underlying or req.instrument_id or "NIFTY"
    try:
        u = validate_underlying(raw_u)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    tf = (req.timeframe or req.candle_timeframe or "5M").upper()
    if tf not in ("1M", "3M", "5M", "15M", "1H", "1D"):
        raise HTTPException(status_code=422, detail=f"Unknown timeframe '{tf}'. Use 1M, 3M, 5M, 15M, 1H, or 1D.")
    raw_dir = (req.direction or "LONG_CALL").upper()
    if raw_dir in ("BULLISH", "LONG", "BUY"):
        dir_val = "LONG_CALL"
    elif raw_dir in ("BEARISH", "SHORT", "SELL"):
        dir_val = "LONG_PUT"
    elif raw_dir not in ("LONG_CALL", "LONG_PUT"):
        raise HTTPException(status_code=422, detail=f"Unknown direction '{req.direction}'. Use LONG_CALL / LONG_PUT (or BULLISH / BEARISH).")
    else:
        dir_val = raw_dir

    market_svc = MarketService()
    try:
        quote = await asyncio.wait_for(market_svc.get_quote(u), timeout=6.0)
    except Exception:
        quote = None
    quote_ok = quote is not None and getattr(quote, "ltp", None) is not None and not _quote_is_fallback(quote)
    spot = Decimal(str(quote.ltp)) if quote_ok else None
    if spot is None:
        if req.current_price or req.trigger or req.trigger_level:
            spot = Decimal(str(req.current_price or req.trigger or req.trigger_level))
        else:
            raise HTTPException(
                status_code=503,
                detail=f"Live price for {u} is unavailable (feed degraded) and no manual price was supplied. Retry when LIVE.",
            )
    tick = Decimal("0.05")

    is_put = "PUT" in dir_val or "BEARISH" in dir_val
    trig_val = req.trigger or req.trigger_level
    min_gap = normalize_price(max(spot * Decimal("0.001"), Decimal("15.0")), tick)
    trigger = normalize_price(trig_val or (spot - min_gap if is_put else spot + min_gap), tick)
    entry_min = normalize_price(req.entry_min or (trigger - Decimal("5.0") if is_put else trigger), tick)
    entry_max = normalize_price(req.entry_max or (trigger if is_put else trigger + Decimal("5.0")), tick)

    if is_put:
        stop_loss = normalize_price(req.stop_loss or (spot * Decimal("1.005")), tick)
        risk_pts = abs(stop_loss - entry_max)
        t1 = normalize_price(req.target_1 or (entry_min - (risk_pts * Decimal("1.5"))), tick)
        t2 = normalize_price(req.target_2 or (entry_min - (risk_pts * Decimal("3.0"))), tick)
    else:
        stop_loss = normalize_price(req.stop_loss or (spot * Decimal("0.995")), tick)
        risk_pts = abs(entry_min - stop_loss)
        t1 = normalize_price(req.target_1 or (entry_max + (risk_pts * Decimal("1.5"))), tick)
        t2 = normalize_price(req.target_2 or (entry_max + (risk_pts * Decimal("3.0"))), tick)

    rr_t1 = float((abs(t1 - (entry_min if is_put else entry_max)) / risk_pts).quantize(Decimal("0.1"))) if risk_pts > 0 else 1.5
    rr_t2 = float((abs(t2 - (entry_min if is_put else entry_max)) / risk_pts).quantize(Decimal("0.1"))) if risk_pts > 0 else 3.0

    # ── Level sanity: reject incoherent manuals instead of registering doomed signals ──
    if risk_pts <= 0:
        raise HTTPException(status_code=400, detail="Stop-loss must differ from entry (zero risk points).")
    if is_put and not (stop_loss > entry_max and t1 < entry_min and t2 < t1):
        raise HTTPException(status_code=400, detail="PUT levels incoherent: need SL > entry > T1 > T2.")
    if not is_put and not (stop_loss < entry_min and t1 > entry_max and t2 > t1):
        raise HTTPException(status_code=400, detail="CALL levels incoherent: need SL < entry < T1 < T2.")

    try:
        opt_type = "CE" if "CALL" in dir_val else "PE"
        contract = resolve_option_contract(u, spot, opt_type, strike_offset=0)
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))

    fsm_st = "CONFIRMED" if (req.execute_paper or req.status == "CONFIRMED") else "ARMED"

    strat_val = req.strategy.upper()
    if strat_val in ("VWAP_REJECTION", "VWAP"):
        strat_val = "VWAP_SCALP"
    if strat_val not in STRATEGY_REGISTRY:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown strategy '{req.strategy}'. Valid: {sorted(STRATEGY_REGISTRY.keys())}",
        )

    # ── Trigger integrity: reject born-triggered / no-edge manuals ──
    from app.signals.trigger_gate import check_trigger_integrity
    gate = check_trigger_integrity(
        underlying=u,
        strategy=strat_val,
        direction=dir_val,
        spot_price=spot,
        entry_min=entry_min,
        entry_max=entry_max,
        trigger=trigger,
        stop_loss=stop_loss,
        target_1=t1,
        target_2=t2,
        risk_points=risk_pts,
        risk_reward_t1=rr_t1,
        risk_reward_t2=rr_t2,
    )
    if not gate.passed:
        raise HTTPException(status_code=400, detail=f"{gate.reason_code}: {gate.message}")

    is_scalp_setup = req.is_scalp or (req.signal_type == "SCALP") or (tf in ("1M", "3M")) or (strat_val in ("VWAP_SCALP", "MICRO_MOMENTUM", "EMA_RIBBON", "GAMMA_SPIKE"))
    sig_type = "SCALP" if is_scalp_setup else (req.signal_type or "INTRADAY")
    ttl_s = req.time_stop_seconds or (180 if is_scalp_setup else 300)

    instance = SignalInstance(
        underlying=u,
        strategy=strat_val,
        direction=dir_val,
        timeframe=tf,
        spot_price=spot,
        signal_type=sig_type,
        is_scalp=is_scalp_setup,
        entry_min=entry_min,
        entry_max=entry_max,
        trigger=trigger,
        stop_loss=stop_loss,
        initial_stop_loss=stop_loss,
        current_stop_loss=stop_loss,
        target_1=t1,
        target_2=t2,
        t1_price=t1,
        t2_price=t2,
        risk_points=risk_pts,
        risk_reward_t1=rr_t1,
        risk_reward_t2=rr_t2,
        ttl_seconds=ttl_s,
        runner_ttl_seconds=req.runner_ttl_seconds,
        confidence=req.confidence or 80.0,
        confluence_breakdown={"technical": 80.0, "mtf": 75.0, "fno": 75.0, "regime": 80.0, "ai": 75.0},
        rationale=req.rationale or [f"Manual {req.strategy} setup on {u}"],
        option_contract=contract.model_dump(),
        fsm_state=fsm_st,
    )
    signal_fsm.register(instance)

    # Register into Signal Audit Ledger
    try:
        from app.signals.audit_ledger import signal_audit_ledger
        signal_audit_ledger.record_signal_created(
            signal_id=instance.signal_id,
            underlying=instance.underlying,
            strategy=instance.strategy,
            direction=instance.direction,
            timeframe=instance.timeframe,
            spot_price=float(instance.spot_price),
            trigger=float(instance.trigger),
            stop_loss=float(instance.stop_loss),
            target_1=float(instance.target_1),
            target_2=float(instance.target_2),
            confidence=float(instance.confidence),
            option_contract=instance.option_contract,
            lots=req.lots or 1,
            status=instance.fsm_state,
        )
    except Exception as ae:
        logger.warning("audit_record_created_failed", error=str(ae))

    # Authoritative Supabase PostgreSQL Persistence
    try:
        from app.signals.signals_persistence import persist_executed_signal
        await persist_executed_signal(instance)
    except Exception as se:
        logger.warning("generate_signal_supabase_persist_failed", signal_id=instance.signal_id, error=str(se))

    paper_result = None
    if req.execute_paper:
        try:
            paper_result = await signal_paper_engine.execute_signal(instance.signal_id, lots_override=req.lots or 1)
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
                candle_timeframe=tf,
                setup_type=req.strategy,
                direction="BULLISH" if "CALL" in dir_val else "BEARISH",
                status=instance.fsm_state,
                trigger_level=float(instance.trigger),
                current_price=float(instance.spot_price),
                stop_loss=float(instance.stop_loss),
                confidence=float(instance.confidence),
                paper_order_id=paper_result.order_id if paper_result else None,
                paper_fill_price=paper_result.fill_price if paper_result else None,
                paper_filled_qty=paper_result.quantity if paper_result else None,
                paper_status="FILLED" if paper_result else None,
                paper_side="BUY" if "CALL" in dir_val else "SELL",
            )
            ids = await telegram_notification_queue.publish_signal_event(ev)
            telegram_res["enqueued"] = len(ids)
        except Exception as te:
            logger.warning("generate_telegram_dispatch_failed", error=str(te))

    # Broadcast P0 Signal Creation via SSE
    await signal_sse_hub.broadcast("signal_created", instance.model_dump(), priority="P0")

    sig_dump = instance.model_dump()
    sig_dump["instrument_id"] = instance.underlying
    sig_dump["direction"] = "BULLISH" if "CALL" in instance.direction else "BEARISH"
    sig_dump["created_at_utc"] = instance.created_at_utc

    paper_order_dict = None
    if paper_result:
        paper_order_dict = {
            "order_id": paper_result.order_id,
            "status": paper_result.status,
            "side": "BUY" if "CALL" in instance.direction else "SELL",
            "quantity": paper_result.quantity,
            "underlying": instance.underlying,
            "fill_price": paper_result.fill_price,
        }

    return {
        "success": True,
        "signal": sig_dump,
        "paper_order": paper_order_dict,
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


# ── 11. TELEGRAM PREVIEW ──────────────────────────────────────────────

@router.post("/preview")
def preview_signal(req: PreviewSignalRequest):
    """Generate a Telegram alert formatted preview without publishing."""
    from app.institutional.telegram_templates import render_event_message
    from app.institutional.telegram_notifications import SignalEvent

    u = (req.underlying or req.instrument_id or "NIFTY").upper()
    tf = (req.timeframe or req.candle_timeframe or "5M").upper()
    dir_val = "BULLISH" if ("CALL" in req.direction.upper() or "BULLISH" in req.direction.upper()) else "BEARISH"
    strat = (req.strategy or req.setup_type or "BREAKOUT").upper()
    trig = req.trigger if req.trigger is not None else req.trigger_level
    status_str = (req.status or "CONFIRMED").upper()
    ev_type = "SIGNAL_CONFIRMED" if status_str == "CONFIRMED" else ("SIGNAL_TRIGGERED" if status_str == "TRIGGERED" else "POSSIBLE_SETUP")

    ev = SignalEvent(
        event_type=ev_type,
        signal_id=f"preview-{uuid.uuid4().hex[:8]}",
        instrument=u,
        candle_timeframe=tf,
        setup_type=strat,
        direction=dir_val,
        status=status_str,
        trigger_level=float(trig) if trig is not None else None,
        stop_loss=float(req.stop_loss) if req.stop_loss is not None else None,
        target_low=float(req.target_1) if req.target_1 is not None else None,
        target_high=float(req.target_2) if req.target_2 is not None else None,
        confidence=float(req.confidence) if req.confidence is not None else None,
    )
    text = render_event_message(ev)
    return {
        "event_type": ev.event_type,
        "instrument": ev.instrument,
        "preview": text,
        "event": ev.model_dump(),
    }


# ── 12. CUSTOM PAPER WALLET CAPITAL ───────────────────────────────────

@router.post("/paper-wallet")
async def set_signals_paper_wallet(
    req: PaperWalletCapitalRequest,
    user: Optional[AuthUser] = Depends(get_current_user),
    session: Optional[AsyncSession] = Depends(get_db_session),
):
    """Set custom virtual capital for the paper trading wallet."""
    from app.services.paper_service import paper_service
    from app.api.paper import _parse_user_uuid
    try:
        user_uuid = _parse_user_uuid(user)
        summary = await paper_service.set_initial_capital_async(req.capital, session, user_uuid)
        return {
            "status": "success",
            "data": summary.model_dump(mode="json"),
            "capital": summary.virtual_capital,
            "available_margin": summary.available_margin,
        }
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 13. SINGLE SIGNAL QUERY (FALLTHROUGH) ─────────────────────────────

@router.get("/{signal_id}")
def get_signal_by_id(signal_id: str):
    sig = signal_fsm.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    return sig.model_dump()
