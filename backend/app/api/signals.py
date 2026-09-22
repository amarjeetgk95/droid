"""
Unified Signal Centre API Router
Institutional-Grade Endpoints for Indian Index Options (NIFTY, BANKNIFTY, SENSEX) on FYERS.
"""
from __future__ import annotations

import asyncio
import time
import uuid
from decimal import Decimal
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.security import AuthUser, get_current_user
from app.services.market_service import MarketService
from app.signals.audit_ledger import signal_audit_ledger
from app.signals.contract_resolver import (
    APPROVED_UNDERLYINGS,
    calculate_position_sizing,
    validate_underlying,
)
from app.signals.fsm import signal_fsm
from app.signals import manual_signal_service
from app.signals.manual_signal_service import InvalidManualSignal
from app.signals.market_guard import ensure_market_open_or_raise_http
from app.signals.outcome_tracker import outcome_tracker
from app.signals.paper_engine import signal_paper_engine
from app.signals.scanner import scanner_engine
from app.signals.sse import signal_sse_hub
from app.signals.strategies import (
    INTRADAY_STRATEGY_NAMES,
    REGISTRY_VERSION,
    SCALP_STRATEGY_NAMES,
    STRATEGY_ENABLED,
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/signals", tags=["signals"])

# ── P0-5 AUTH + closed-market privilege ──────────────────────────────────
# Operator roles allowed to mint closed-market signals (testing/demo only).
_OPERATOR_ROLES = frozenset({"admin", "operator"})


def _operator_email(user: AuthUser | None) -> str:
    try:
        return str(getattr(user, "email", "") or "unknown")
    except Exception:
        return "unknown"


def _require_closed_market_privilege(user: AuthUser | None, allow_closed: bool, confirm: bool) -> None:
    """Closed-market mint is fail-closed in every env (dev included).

    allow_closed_market=True requires confirm=True + operator role
    (admin/operator). No legacy no-confirm bypass: unconfirmed closed-market
    mint is 403. Confirmed closed-market mints are watermarked DEMO/CLOSED-MARKET
    downstream and are never plain live.
    """
    if not allow_closed:
        return
    role = str(getattr(user, "role", "") or "").lower()
    email = _operator_email(user)
    if role in _OPERATOR_ROLES and confirm:
        logger.info("closed_market_generation_authorized", user_email=email, role=role)
        return
    raise HTTPException(
        status_code=403,
        detail="Closed-market generation requires confirm=true + operator role (admin/operator).",
    )


# ── Request / Response Models ──────────────────────────────────────────

class GenerateSignalRequest(BaseModel):
    underlying: str | None = Field(default=None, description="NIFTY / BANKNIFTY / SENSEX")
    instrument_id: str | None = Field(default=None, description="Compatibility alias for underlying")
    strategy: str = "BREAKOUT"
    direction: str = "LONG_CALL"
    timeframe: str | None = Field(default=None, description="1M, 3M, 5M, 15M, 1H, 1D")
    candle_timeframe: str | None = Field(default=None, description="Compatibility alias for timeframe")
    status: str | None = None
    signal_type: str | None = Field(default="INTRADAY", description="SCALP or INTRADAY")
    is_scalp: bool = Field(default=False, description="Flag indicating high-frequency scalp setup")
    time_stop_seconds: int | None = None
    runner_ttl_seconds: int | None = None
    entry_min: float | None = None
    entry_max: float | None = None
    trigger: float | None = None
    trigger_level: float | None = None
    current_price: float | None = None
    stop_loss: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    confidence: float | None = Field(default=None, description="Measured confidence only; None when unmeasured (UNVETTED, never 80.0 default)")
    execute_paper: bool = Field(default=False, description="Auto-execute paper order")
    lots: int | None = Field(default=None, description="Optional custom lots")
    notify_telegram: bool = Field(default=True, description="Enqueue Telegram notification")
    rationale: list[str] | None = None
    allow_closed_market: bool = Field(default=False, description="Allow generating signal when market is closed (for testing/demo)")
    confirm: bool = Field(default=False, description="Explicit operator confirmation for closed-market generation (required with allow_closed_market)")
    idempotency_key: str | None = Field(default=None, description="Client idempotency key: retries return the original signal")



class AutoDetectRequest(BaseModel):
    underlying: str
    strategy: str = "BREAKOUT"
    timeframe: str = "5M"


class ExecutePaperRequest(BaseModel):
    lots: int | None = Field(default=None, description="Optional custom lots override")
    quantity: int | None = Field(default=None, description="Optional custom quantity override")
    risk_percent: float = Field(default=2.0, description="Risk capital % for sizing")


class PreviewSignalRequest(BaseModel):
    instrument_id: str | None = None
    underlying: str | None = None
    candle_timeframe: str | None = "5M"
    timeframe: str | None = None
    direction: str = "BULLISH"
    status: str = "CONFIRMED"
    trigger_level: float | None = None
    trigger: float | None = None
    stop_loss: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    confidence: float | None = None
    setup_type: str | None = "BREAKOUT"
    strategy: str | None = None


class PaperWalletCapitalRequest(BaseModel):
    capital: float


# ── 1. ACTIVE SIGNALS LIST ───────────────────────────────────────────

VALID_INSTRUMENTS = {"NIFTY", "BANKNIFTY", "SENSEX"}
VALID_DESKS = {"SCALP", "INTRADAY", "ALL"}


def _quote_is_fallback(quote: Any) -> bool:
    """Delegate to the unified quote-quality policy (single source of truth)."""
    try:
        from app.signals.quote_quality import is_fallback_quote

        return is_fallback_quote(quote)
    except Exception:
        return False


@router.get("/active")
async def list_active_signals(
    instrument: str | None = Query(None, description="Filter by NIFTY / BANKNIFTY / SENSEX"),
    strategy: str | None = Query(None, description="Filter by strategy name"),
    status: str | None = Query(None, description="Filter by FSM state"),
    desk: str | None = Query(None, description="Filter by desk: SCALP, INTRADAY, or ALL"),
    is_scalp: bool | None = Query(None, description="Filter specifically for scalp signals"),
):
    """
    Returns active signals with live price distance, contract specs, R:R metrics, and desk categorization.
    Never fails hard on a stale quote — per-signal quotes degrade independently (allSettled pattern).
    """
    if instrument and instrument.upper() not in VALID_INSTRUMENTS:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown instrument '{instrument}'. Approved universe: {sorted(VALID_INSTRUMENTS)}",
        )
    if desk and desk.upper() not in VALID_DESKS:
        raise HTTPException(status_code=422, detail=f"Unknown desk '{desk}'. Use SCALP, INTRADAY, or ALL.")
    return await build_active_signals_payload(
        instrument=instrument,
        strategy=strategy,
        status=status,
        desk=desk,
        is_scalp=is_scalp,
    )


async def build_active_signals_payload(
    instrument: str | None = None,
    strategy: str | None = None,
    status: str | None = None,
    desk: str | None = None,
    is_scalp: bool | None = None,
) -> dict[str, Any]:
    """Compose the active-signals payload (FSM state + live quote distances).

    Shared by `GET /api/v1/signals/active` and the CommandView composition leg
    (`GET /api/v1/view/command`) so the two surfaces can never drift. Callers
    must validate `instrument`/`desk` against their approved sets first.
    """
    include_terminal = (status == "ALL" or (status is not None and status in ("CLOSED", "EXPIRED", "INVALIDATED", "TARGET_2_HIT", "STOP_LOSS_HIT", "TIME_STOP_HIT", "RUNNER_TIME_STOP_HIT")))
    signals = signal_fsm.list_active(underlying=instrument, strategy=strategy, include_terminal=include_terminal)

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
        except TimeoutError:
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
            if quote is not None and getattr(quote, "ltp", None) is not None and float(quote.ltp) > 0:
                curr_p = Decimal(str(quote.ltp))
                trig = s.trigger if s.trigger and s.trigger > 0 else None
                if trig:
                    diff = abs(curr_p - trig)
                    distance_pts = float(diff.quantize(Decimal("0.05")))
                    distance_pct = float((diff / trig * Decimal(100)).quantize(Decimal("0.01")))
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
async def run_scanner(desk: str | None = Query(None, description="SCALP, INTRADAY, or ALL")):
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


@router.get("/analytics/funnel")
def get_signal_funnel_analytics(
    strategy: str | None = Query(None, description="Optional strategy filter"),
    underlying: str | None = Query(None, description="Optional underlying filter (NIFTY, BANKNIFTY, SENSEX)"),
):
    """
    Returns real-time and daily aggregated Signal Funnel metrics, top gate blockers,
    and per-strategy conversion metrics to explain zero-signal periods.
    """
    try:
        return scanner_engine.get_funnel_analytics(strategy_filter=strategy, underlying_filter=underlying)
    except Exception as e:
        logger.error("signal_funnel_analytics_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch funnel analytics: {str(e)[:150]}")


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

    # Immutable explain bundle — build on-the-fly for old signals so UI never gets null
    # Thresholds/weights are single-sourced from scoring_weights.json. A missing
    # config yields threshold_armed=None + INSUFFICIENT_DATA (never a silent 78.0).
    try:
        import json as _json
        from pathlib import Path as _Path

        _sw = {}
        for _p in (
            _Path(__file__).resolve().parents[2] / "config" / "scoring_weights.json",
            _Path("backend/config/scoring_weights.json"),
        ):
            if _p.exists():
                _sw = _json.loads(_p.read_text(encoding="utf-8"))
                break
        _armed_raw = ((_sw.get("thresholds", {}) or {}).get("armed"))
        _armed_thr = float(_armed_raw) if _armed_raw is not None else None
        _threshold_status = "MEASURED" if _armed_thr is not None else "INSUFFICIENT_DATA"
        _wver = (_sw.get("version", 2))
        _wf = dict((_sw.get("weights_fraction", {}) or {})) or None
        if _armed_thr is None or _wf is None:
            _threshold_status = "INSUFFICIENT_DATA"
    except Exception:
        _armed_thr, _wver, _wf = None, 2, None
        _threshold_status = "INSUFFICIENT_DATA"
    explain = getattr(sig, "explain", None)
    if not explain:
        try:
            from app.signals.confluence import DEFAULT_WEIGHTS
            from app.signals.explain import build_signal_explain
            cb = sig.confluence_breakdown or {}
            ai_adv = {"status": cb.get("ai_status", "UNAVAILABLE"), "score": cb.get("ai")}
            ml_sc = cb.get("ml_score")
            ml_p = {"is_available": ml_sc is not None, "bullish_pct": ml_sc, "bearish_pct": ml_sc} if ml_sc is not None else None
            inputs_snapshot = {
                "spot": float(sig.spot_price),
                "vwap": float(sig.spot_price),
                "regime": sig.regime_at_confirmation or "RANGE",
                "indicators": {},
                "fno": {},
                "mtf": {},
            }
            data_health = {"fno_degraded": bool(cb.get("fno_degraded", False)), "vwap_degraded": False, "vwap_coverage_pct": 100.0}
            _sig_conf = float(sig.confidence) if getattr(sig, "confidence", None) is not None else None
            explain = build_signal_explain(
                sig, _sig_conf, ai_adv, ml_p, None,
                {"weights_fraction": (_wf or dict(DEFAULT_WEIGHTS)), "version": _wver},
                {"armed": _armed_thr}, [], inputs_snapshot, data_health,
            )
        except Exception:
            explain = None

    _conf_val = getattr(sig, "confidence", None)
    _conf_status = cb.get("confidence_status") if isinstance(cb, dict) and cb.get("confidence_status") else ("UNVETTED" if _conf_val is None else "MEASURED")
    return {
        "signal": sig.model_dump(),
        "explain": explain,
        "weights_version": _wver,
        "threshold_armed": _armed_thr,
        "threshold_status": _threshold_status,
        "confidence": _conf_val,
        "confidence_status": _conf_status,
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
    underlying: str | None = Query(None, description="Filter by NIFTY / BANKNIFTY / SENSEX"),
    strategy: str | None = Query(None, description="Filter by strategy"),
    status: str | None = Query(None, description="Filter by status: WON, LOST, EXECUTED, ARMED, etc."),
    limit: int = Query(100, description="Max records to return"),
):
    """
    Authoritative Signal Audit Ledger showing real trade lifecycle,
    actual fill vs trigger, current market LTP, duration, and exact realized & unrealized P&L.
    """
    from app.signals.audit_ledger import signal_audit_ledger
    from app.signals.contract_resolver import APPROVED_UNDERLYINGS

    # Lazy-restore if ledger is empty in memory (e.g. startup timeout or cold start)
    if len(signal_audit_ledger._trades) == 0:
        try:
            from app.signals.signals_persistence import restore_signals_state_local, restore_signals_from_db
            restored = restore_signals_state_local()
            if restored == 0:
                await restore_signals_from_db()
        except Exception as lz_err:
            logger.debug("audit_ledger_lazy_restore_skipped", error=str(lz_err)[:150])

    # Sync with FSM and Paper Service
    signal_audit_ledger.sync_with_fsm()
    signal_audit_ledger.sync_with_paper_service()

    # Fetch live quotes to compute real-time MTM only during active market sessions with valid live ticks
    from app.models.market import DataStatus
    from app.services.calendar_service import calendar_service
    if calendar_service.can_trade_now().allowed:
        # Refresh open option contracts so MTM has fresh broker LTPs
        from app.signals.option_marks import option_mark_service
        open_symbols = signal_audit_ledger.get_open_option_symbols()
        if open_symbols:
            try:
                await option_mark_service.refresh_and_register(open_symbols)
            except Exception:
                pass

        market_svc = MarketService()
        quotes: dict[str, float] = {}
        for u in APPROVED_UNDERLYINGS:
            try:
                q = await market_svc.get_quote(u)
                if q and getattr(q, "ltp", None) is not None and getattr(q, "status", None) == DataStatus.LIVE and float(q.ltp) > 0:
                    quotes[u] = float(q.ltp)
            except Exception:
                pass

        if quotes:
            signal_audit_ledger.update_live_quotes_batch(quotes)

    trades = signal_audit_ledger.list_trades(underlying=underlying, strategy=strategy, status=status, limit=limit)
    # Never serve test/demo scaffolding or voided (quarantined) trades as history.
    def _is_test_trade(t: Any) -> bool:
        sid = str(getattr(t, "signal_id", "") or "").lower()
        if str(getattr(t, "status", "") or "").upper() == "VOID":
            return True
        return sid.startswith(("sig-test-", "sig-wallet-", "test-", "sig-persist-sanitize"))
    trades = [t for t in trades if not _is_test_trade(t)]
    summary = signal_audit_ledger.get_summary_metrics()
    from app.signals.safety.feed_health_monitor import feed_health_monitor
    feed_health = feed_health_monitor.get_telemetry()
    return {
        "trades": [t.model_dump() for t in trades],
        "count": len(trades),
        "summary": summary,
        "feed_health": feed_health,
        "timestamp_ms": int(time.time() * 1000),
    }


class VoidTradesRequest(BaseModel):
    signal_ids: list[str] = Field(default_factory=list, description="Trade IDs to quarantine")
    reason: str = Field(default="VOID_CORRUPT_HISTORY", description="Quarantine reason kept on the record")


@router.post("/audit/void")
async def void_audit_trades(
    req: VoidTradesRequest,
    user: AuthUser = Depends(get_current_user),
):
    """Quarantine trades: kept as evidence, excluded from P&L and ledger.
    Use for demonstrably corrupt history instead of deleting it."""
    from app.signals.audit_ledger import signal_audit_ledger

    _email = _operator_email(user)
    logger.info("audit_void_requested", user_email=_email, count=len(req.signal_ids or []))
    if not req.signal_ids:
        raise HTTPException(status_code=400, detail="Pass signal_ids to void.")
    voided: list[str] = []
    for sid in req.signal_ids[:100]:
        try:
            if signal_audit_ledger.void_trade(str(sid), f"{req.reason} (by {_email})"):
                voided.append(str(sid))
        except Exception as e:
            logger.warning("void_trade_failed", signal_id=sid, error=str(e), user_email=_email)
    try:
        await signal_sse_hub.broadcast(
            "audit_voided",
            {"voided_ids": voided, "count": len(voided), "by": _email},
            priority="P0",
        )
    except Exception:
        pass
    return {
        "status": "success",
        "voided_count": len(voided),
        "voided_ids": voided,
        "summary": signal_audit_ledger.get_summary_metrics(),
        "timestamp_ms": int(time.time() * 1000),
    }


@router.post("/audit/sanitize")
async def sanitize_signal_audit(
    user: AuthUser = Depends(get_current_user),
):
    """
    Trigger comprehensive memory and database sanitization of audit ledger:
    - Purges corrupted prices, ghost signals, and phantom exposure
    - Bounds option buying losses to 100% of premium
    - Reconciles any mismatched spot vs premium domain levels
    """
    from app.signals.audit_ledger import signal_audit_ledger
    from app.signals.signals_persistence import (
        restore_signals_from_db,
        sanitize_persisted_signals,
    )

    _email = _operator_email(user)
    logger.info("audit_sanitize_requested", user_email=_email)

    db_count = await restore_signals_from_db()
    mem_count = sanitize_persisted_signals()
    summary = signal_audit_ledger.get_summary_metrics()
    try:
        await signal_sse_hub.broadcast(
            "audit_sanitized",
            {"db_restored_repaired": db_count, "memory_sanitized": mem_count, "by": _email},
            priority="P0",
        )
    except Exception:
        pass

    return {
        "status": "success",
        "db_restored_repaired": db_count,
        "memory_sanitized": mem_count,
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
    before_ms: int | None = Field(default=None, description="Delete signals created before this epoch-ms (datewise clear)")
    underlying: str | None = Field(default=None, description="Filter: NIFTY / BANKNIFTY / SENSEX")
    strategy: str | None = Field(default=None, description="Filter by strategy name")
    status: str | None = Field(default=None, description="Filter by FSM/audit status")
    delete_all: bool = Field(default=False, description="Delete everything matching the filters")
    confirm_all: bool = Field(default=False, description="Required safety flag when delete_all has no other selector")


@router.post("/bulk-delete")
async def bulk_delete_signals(
    req: BulkDeleteRequest,
    user: AuthUser = Depends(get_current_user),
):
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

        for s in signal_fsm.list_active(include_terminal=True):
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

    _email = _operator_email(user)
    logger.info("signals_bulk_delete_requested", user_email=_email, requested=len(ids))
    try:
        await signal_sse_hub.broadcast(
            "signals_bulk_deleted",
            {"signal_ids": deleted, "count": len(deleted), "by": _email},
            priority="P0",
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
async def delete_signal_by_id(
    signal_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """
    Authority to delete a signal: removes from FSM, Audit Ledger, Supabase,
    squares off any open paper position, and broadcasts signal_deleted event.
    """
    _email = _operator_email(user)
    logger.info("signal_delete_requested", signal_id=signal_id, user_email=_email)
    res = await _delete_signal_core(signal_id)

    # Broadcast SSE (P0-5: include operator for audit trail)
    await signal_sse_hub.broadcast(
        "signal_deleted", {"signal_id": signal_id, "by": _email}, priority="P0"
    )

    return {
        "status": "success",
        "message": f"Signal {signal_id} deleted successfully",
        "fsm_deleted": res["fsm_deleted"],
        "audit_deleted": res["audit_deleted"],
    }


# ── 6. 1-CLICK PAPER TRADING EXECUTION ────────────────────────────────

@router.post("/{signal_id}/execute-paper")
async def execute_signal_paper(
    signal_id: str,
    req: ExecutePaperRequest | None = None,
    user: AuthUser = Depends(get_current_user),
):
    """
    1-Click manual execution of any active signal into the Paper Trading Engine.
    Fails closed if the exchange session is closed.
    """
    _email = _operator_email(user)
    from app.services.calendar_service import calendar_service
    perm = calendar_service.can_trade_now()
    if not perm.allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Market is closed ({perm.reason}: NSE trading hours 09:15 - 15:30 IST). Manual paper execution is disabled.",
        )
    logger.info("paper_execute_requested", signal_id=signal_id, user_email=_email)

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
        if not result.success or result.status == "REJECTED":
            raise HTTPException(status_code=400, detail=result.message)

        # Long options are always bought: report the engine's actual action,
        # never a direction-derived SELL (a PUT is still a BUY of the option).
        _side_raw = str(getattr(result, "side", "") or "").upper()
        side_val = "SELL" if _side_raw.startswith("SELL") else "BUY"

        # Broadcast P0 execution event (P0-5: include operator for audit trail)
        _exec_payload = result.model_dump()
        _exec_payload["executed_by"] = _email
        await signal_sse_hub.broadcast("paper_execution", _exec_payload, priority="P0")
        res_data = result.model_dump()
        res_data["executed_by"] = _email
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
        raise HTTPException(status_code=500, detail=f"Paper execution failed: {e!s}")


# ── 7. AUTO-DETECT LIVE SETUP (PRE-FILL GENERATOR) ────────────────────

@router.post("/auto-detect")
async def auto_detect_setup(
    req: AutoDetectRequest,
    user: AuthUser = Depends(get_current_user),
):
    """
    Evaluates live candles and indicators to automatically pre-fill realistic Entry, SL, and Target levels.
    Fail-closed: detected=False carries no entry/stop/target (null) and
    confidence=None + INSUFFICIENT_DATA — never a tradable baseline.
    """
    _email = _operator_email(user)
    logger.info("auto_detect_requested", underlying=req.underlying, user_email=_email)
    ensure_market_open_or_raise_http(detail_prefix="Auto-detect setup blocked")
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
            _cand = selected.model_dump()
            try:
                await signal_sse_hub.broadcast(
                    "auto_detect",
                    {"underlying": u, "detected": True, "by": _email},
                    priority="P2",
                )
            except Exception:
                pass
            return {
                "detected": True,
                "candidate": _cand,
                "message": f"Detected {selected.strategy} {selected.direction} on {req.underlying}",
            }

        # Baseline levels require a live quote — never invent them off a
        # hardcoded spot (truth-of-wall: no 24800-style fallbacks).
        spot = await manual_signal_service.resolve_live_spot(u)
        if spot is None:
            raise HTTPException(
                status_code=503,
                detail=f"Live price for {u} is unavailable (feed degraded). Auto-detect needs a live quote.",
            )

        _baseline = manual_signal_service.build_baseline_candidate(u, req.strategy, req.timeframe, spot)
        return {
            "detected": False,
            "candidate": _baseline,
            "confidence": None,
            "confidence_status": "INSUFFICIENT_DATA",
            "tradable": False,
            "message": "No active setup triggered; no tradable levels (fail-closed, INSUFFICIENT_DATA).",
        }
    except HTTPException:
        # A degraded feed raises 503 above — never downgrade it to 400.
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 8. MANUAL SIGNAL GENERATION ───────────────────────────────────────

@router.post("/generate")
async def generate_signal(
    req: GenerateSignalRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    """
    Manual authoritative signal generation with FSM registration, optional paper execution, and Telegram dispatch.
    Rejects unknown underlyings (422) and incoherent levels (400); never fabricates fills off fallback quotes.
    P0-5: authenticated; allow_closed_market=True requires confirm=true + operator role.
    """
    _email = _operator_email(user)
    # P0-5 role gate BEFORE the market-session check (coordinate via imports; drift
    # math itself stays in manual_signal_service owned by another agent).
    _require_closed_market_privilege(user, req.allow_closed_market, req.confirm)
    ensure_market_open_or_raise_http(allow_closed=req.allow_closed_market, detail_prefix="Manual signal generation blocked")
    logger.info(
        "signal_generate_requested",
        user_email=_email,
        underlying=req.underlying or req.instrument_id,
        allow_closed=req.allow_closed_market,
    )
    try:
        # Idempotency-Key header (or body field) → same key returns the original signal.
        header_key: str | None = None
        try:
            header_key = request.headers.get("Idempotency-Key") or request.headers.get("idempotency-key")
        except Exception:
            header_key = None
        result = await manual_signal_service.generate(req, idempotency_key=header_key or req.idempotency_key)
        # P0-5: audit + SSE payload carry the operator identity (manual service owns
        # drift math; we only annotate provenance here via imports).
        # Closed-market mints are watermarked DEMO/CLOSED-MARKET, never plain live.
        try:
            result["created_by"] = _email
            _sig = (result.get("signal") or {})
            _sid = _sig.get("signal_id", "unknown")
            if bool(req.allow_closed_market):
                result["watermark"] = "DEMO/CLOSED-MARKET"
                result["market_session"] = "CLOSED-MARKET"
                result["live"] = False
                try:
                    _sig["watermark"] = "DEMO/CLOSED-MARKET"
                    _sig["market_session"] = "CLOSED-MARKET"
                    _sig["live"] = False
                except Exception:
                    pass
            # Surface explicit confidence status: None means UNVETTED, never 80.0.
            try:
                if _sig.get("confidence") is None and "confidence_status" not in _sig:
                    _sig["confidence_status"] = "UNVETTED"
                if "confidence_status" not in result and _sig.get("confidence_status"):
                    result["confidence_status"] = _sig.get("confidence_status")
            except Exception:
                pass
        except Exception:
            _sid = "unknown"
        logger.info("signal_generated", signal_id=_sid, user_email=_email)
        try:
            await signal_sse_hub.broadcast(
                "signal_created_audit",
                {"signal_id": _sid, "created_by": _email, "allow_closed_market": bool(req.allow_closed_market)},
                priority="P0",
            )
        except Exception:
            pass
        return result
    except InvalidManualSignal as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)






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
    """Generate a Telegram alert formatted preview without publishing.

    P0-5: preview fabricates IDs for display only — no market validation is
    performed and nothing is persisted. Do not treat as a tradeable signal.
    """
    from app.institutional.telegram_notifications import SignalEvent
    from app.institutional.telegram_templates import render_event_message

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
        # P0-5 provenance: fabricated preview, never persisted, never validated.
        "disclaimer": "Preview only — no market validation performed; signal_id is fabricated and never persisted. Not tradeable.",
        "persisted": False,
        "market_validated": False,
    }


# ── 12. CUSTOM PAPER WALLET CAPITAL ───────────────────────────────────

@router.post("/paper-wallet")
async def set_signals_paper_wallet(
    req: PaperWalletCapitalRequest,
    user: AuthUser | None = Depends(get_current_user),
    session: AsyncSession | None = Depends(get_db_session),
):
    """Set custom virtual capital for the paper trading wallet.

    Always controls the anonymous signal paper book — the single shard the
    automated signal engine trades on — never the authenticated per-user
    dashboard wallet (that lives at /api/v1/paper/wallet).
    """
    from app.services.paper_service import paper_service
    try:
        summary = await paper_service.set_initial_capital_async(req.capital, session, None)
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


# ── 12.5 OFFICIAL 11-STRATEGY PORTFOLIO METADATA (§3, §67) ──────────

@router.get("/portfolio-strategies")
def get_portfolio_strategies():
    """Returns the strategy universe grouped by desk, plus the auto-scan freeze.

    Legacy fields (scalp_desk/intraday_desk/all_active_strategies/strategy_count)
    describe the full known universe and are unchanged. New fields expose the
    institutional freeze: auto_scan_strategies (STRATEGY_ENABLED=True) vs
    research_only_strategies, enforced fail-closed by the scanner.
    """
    universe = sorted(SCALP_STRATEGY_NAMES | INTRADAY_STRATEGY_NAMES)
    auto_scan = sorted(n for n in universe if STRATEGY_ENABLED.get(n, False) is True)
    # BREAKOUT alias follows VOLATILITY_BREAKOUT when enabled.
    if STRATEGY_ENABLED.get("VOLATILITY_BREAKOUT") is True and STRATEGY_ENABLED.get("BREAKOUT") is True:
        auto_scan = sorted(set(auto_scan) | {"BREAKOUT"})
    research_only = sorted(n for n in universe if n not in auto_scan)
    return {
        "scalp_desk": sorted(SCALP_STRATEGY_NAMES),
        "intraday_desk": sorted(INTRADAY_STRATEGY_NAMES),
        "all_active_strategies": universe,
        "strategy_count": len(universe),
        "auto_scan_strategies": auto_scan,
        "research_only_strategies": research_only,
        "registry_version": REGISTRY_VERSION,
    }


# ── 12.6 SAFETY & GOVERNANCE CONTROLS (v3.0) ──────────────────────────

@router.get("/feed-health")
def get_feed_health():
    """Returns authoritative system-wide and per-instrument feed health states."""
    from app.signals.safety.feed_health_monitor import feed_health_monitor
    from app.signals.safety.feed_circuit import feed_circuit
    telemetry = feed_health_monitor.get_telemetry()
    telemetry["states"] = feed_circuit.all_states()
    return telemetry


# ── 13. SINGLE SIGNAL QUERY (FALLTHROUGH) ─────────────────────────────

@router.get("/{signal_id}")
def get_signal_by_id(signal_id: str):
    sig = signal_fsm.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Signal not found")
    data = sig.model_dump()

    # Enrich with v3.0 ExecutionIntent and Position if available
    from app.signals.execution_intent import intent_ledger
    from app.signals.position import position_registry

    if sig.execution_intent_id:
        intent = intent_ledger.get(sig.execution_intent_id)
        if intent:
            data["execution_intent"] = intent.model_dump()
    if sig.position_id:
        pos = position_registry.get(sig.position_id)
        if pos:
            data["position"] = pos.model_dump()

    return data


# touch 2026-09-11T16:14:20.4211765+05:30