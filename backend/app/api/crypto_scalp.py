"""
Crypto Scalping & Signal Engine API Endpoints
Provides real-time 1m/5m signals, FSM state inspection, manual generation,
SSE streaming, performance metrics, and chronological execution ledger.
"""
from __future__ import annotations

import time
from decimal import Decimal
from typing import Optional
from fastapi import APIRouter, Query, Body, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import structlog

from app.core.config import settings
from app.crypto_scalp.scanner import crypto_scalp_scanner
from app.crypto_scalp.worker import crypto_scalp_worker
from app.crypto_scalp.fsm import crypto_signal_fsm, CryptoSignalInstance
from app.crypto_scalp.risk_engine import crypto_risk_engine, CryptoStrategySetup
from app.crypto_scalp.trigger_gate import check_crypto_trigger_integrity
from app.crypto_scalp.confluence import crypto_confluence_engine
from app.crypto_scalp.fill_reconciler import crypto_fill_reconciler
from app.crypto_scalp.sse import crypto_sse_hub
from app.crypto_scalp.persistence import (
    fetch_persisted_scalp_signals,
    fetch_execution_records,
    fetch_execution_record_by_id,
    persist_scalp_signal,
)
from app.crypto_scalp.models_execution import (
    CryptoScalpPerformanceMetrics,
    CryptoScalpExecutionRecord,
    CryptoScalpPositionState,
)
from app.crypto_scalp.performance import performance_engine
from app.models.crypto import (
    CryptoScalpSignalsResponse,
    CryptoScalpDiagnostics,
    CryptoScalpConfig,
    CryptoScalpSignal,
    SignalDirection,
    CryptoSignalStatus,
)
from app.services.binance_service import binance_service

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/crypto/scalp-signals", tags=["crypto-scalp"])


# ── Request Models ───────────────────────────────────────────────────

class GenerateCryptoSignalRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT", description="BTCUSDT or ETHUSDT")
    strategy: str = "VWAP_BOUNCE"
    direction: str = "LONG"  # LONG or SHORT
    timeframe: str = "1m"
    spot_price: Optional[float] = None
    trigger: Optional[float] = None
    stop_loss: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    confidence: Optional[float] = 80.0
    execute_paper: bool = True
    rationale: Optional[list[str]] = None


class AutoDetectCryptoRequest(BaseModel):
    symbol: str = "BTCUSDT"
    strategy: str = "VWAP_BOUNCE"
    timeframe: str = "1m"


# ── 1. ACTIVE SIGNALS (COMPATIBILITY + FSM) ──────────────────────────

@router.get("", response_model=CryptoScalpSignalsResponse)
async def get_crypto_scalp_signals(
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g. BTCUSDT, ETHUSDT)"),
    direction: Optional[str] = Query(None, description="Filter by direction: LONG or SHORT"),
):
    """Retrieve active crypto scalp signals across BTC and ETH pairs."""
    try:
        response = await crypto_scalp_scanner.scan_all(force_refresh=False)
        signals = response.signals

        if symbol:
            sym_clean = symbol.upper().strip()
            signals = [s for s in signals if s.symbol == sym_clean or s.asset == sym_clean]

        if direction:
            dir_clean = direction.upper().strip()
            signals = [s for s in signals if s.direction.value == dir_clean]

        btc_count = sum(1 for s in signals if "BTC" in s.symbol)
        eth_count = sum(1 for s in signals if "ETH" in s.symbol)

        return CryptoScalpSignalsResponse(
            signals=signals,
            total_active=len(signals),
            btc_signals=btc_count,
            eth_signals=eth_count,
            diagnostics=response.diagnostics,
            timestamp=response.timestamp,
        )
    except Exception as e:
        logger.error("get_crypto_scalp_signals_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch scalp signals: {str(e)}")


@router.get("/active")
async def get_active_crypto_fsm_signals(
    symbol: Optional[str] = Query(None, description="BTCUSDT / ETHUSDT"),
    strategy: Optional[str] = Query(None, description="Filter by strategy"),
    status: Optional[str] = Query(None, description="Filter by FSM state"),
):
    """
    Returns active Crypto FSM signal instances with live distance to trigger,
    remaining TTL countdown, and two-clock lifecycle telemetry.
    """
    try:
        include_terminal = status == "ALL" or (status is not None and status in ("CLOSED", "EXPIRED", "TARGET_2_HIT", "STOP_LOSS_HIT"))
        signals = crypto_signal_fsm.list_active(symbol=symbol, strategy=strategy, include_terminal=include_terminal)

        dto_list = []
        for s in signals:
            if status and status != "ALL" and s.fsm_state != status:
                continue

            d = s.model_dump()
            d["ttl_remaining_seconds"] = s.ttl_remaining_seconds()
            dto_list.append(d)

        return {
            "signals": dto_list,
            "count": len(dto_list),
            "timestamp_ms": int(time.time() * 1000),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── 2. REAL-TIME SERVER-SENT EVENTS (SSE) STREAM ──────────────────────

@router.get("/stream")
async def stream_crypto_signals(request: Request):
    """
    Real-time low-latency SSE feed for crypto signal creations,
    FSM state transitions, staged fills, and live MTM updates.
    """
    q = crypto_sse_hub.subscribe()
    return StreamingResponse(
        crypto_sse_hub.event_generator(q),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── 3. SCANNER TRIGGERS & AUTO-DETECT ─────────────────────────────────

@router.post("/scan", response_model=CryptoScalpSignalsResponse)
async def trigger_manual_scalp_scan():
    """Force an immediate fresh scalp scan across all crypto pairs."""
    try:
        response = await crypto_scalp_scanner.scan_all(force_refresh=True)
        return response
    except Exception as e:
        logger.error("manual_crypto_scalp_scan_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Manual scan failed: {str(e)}")


@router.post("/auto-detect")
async def auto_detect_crypto_setup(req: AutoDetectCryptoRequest):
    """
    Evaluates live Binance candles and indicators to auto-fill realistic trigger, SL, and targets.
    """
    clean_sym = binance_service.validate_symbol(req.symbol)
    try:
        ctx = await crypto_scalp_scanner.build_context(clean_sym, timeframe=req.timeframe)
        if not ctx:
            raise HTTPException(status_code=503, detail="Binance feed temporarily unreachable.")

        spot = Decimal(str(ctx.current_price))
        atr = Decimal(str(round(ctx.atr_14_1m or 50.0, 2)))
        tick = Decimal("0.01")

        # Baseline levels: 0.04% breakout gap, 1.2x ATR stop loss, 1.5R target
        gap = max(spot * Decimal("0.0004"), atr * Decimal("0.2"))
        trigger = spot + gap
        sl = spot - (atr * Decimal("1.2"))
        risk = trigger - sl
        t1 = trigger + (risk * Decimal("1.5"))
        t2 = trigger + (risk * Decimal("2.5"))

        return {
            "detected": True,
            "symbol": clean_sym,
            "strategy": req.strategy,
            "direction": "LONG",
            "timeframe": req.timeframe,
            "spot_price": float(spot),
            "trigger": float(trigger),
            "stop_loss": float(sl),
            "target_1": float(t1),
            "target_2": float(t2),
            "confidence": 78.0,
            "atr": float(atr),
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 4. MANUAL SIGNAL GENERATION WITH FSM REGISTRATION ─────────────────

@router.post("/generate")
async def generate_crypto_signal(req: GenerateCryptoSignalRequest):
    """
    Manual authoritative signal generation with Trigger Integrity verification,
    Central Risk Engine envelopes, Confluence fusion, FSM registration, and SSE broadcast.
    """
    clean_sym = binance_service.validate_symbol(req.symbol)
    dir_str = req.direction.upper()
    if dir_str not in ("LONG", "SHORT"):
        raise HTTPException(status_code=422, detail="Direction must be LONG or SHORT.")

    # Fetch live quote if not provided
    ticker = await binance_service.get_ticker(clean_sym)
    spot_val = req.spot_price or (float(ticker.price) if ticker else 0.0)
    if spot_val <= 0:
        raise HTTPException(status_code=503, detail="Live market price is unavailable.")

    spot_d = Decimal(str(spot_val))
    is_short = dir_str == "SHORT"

    # Default levels if omitted
    trig_val = req.trigger or (float(spot_d * Decimal("0.9995")) if is_short else float(spot_d * Decimal("1.0005")))
    sl_val = req.stop_loss or (float(spot_d * Decimal("1.006")) if is_short else float(spot_d * Decimal("0.994")))
    risk_val = abs(trig_val - sl_val)
    t1_val = req.target_1 or (trig_val - (risk_val * 1.5) if is_short else trig_val + (risk_val * 1.5))
    t2_val = req.target_2 or (trig_val - (risk_val * 2.5) if is_short else trig_val + (risk_val * 2.5))

    trig_d = Decimal(str(round(trig_val, 2)))
    sl_d = Decimal(str(round(sl_val, 2)))
    t1_d = Decimal(str(round(t1_val, 2)))
    t2_d = Decimal(str(round(t2_val, 2)))

    # 1. Trigger Integrity Gate
    gate_res = check_crypto_trigger_integrity(
        symbol=clean_sym,
        strategy=req.strategy,
        direction=dir_str,
        spot_price=spot_d,
        trigger=trig_d,
        stop_loss=sl_d,
        target_1=t1_d,
        target_2=t2_d,
        is_scalp=req.timeframe in ("1m", "3m"),
        timeframe=req.timeframe,
    )
    if not gate_res.passed:
        raise HTTPException(status_code=400, detail=f"Trigger integrity failure: {gate_res.message}")

    # 2. Central Risk Engine Envelopes
    setup = CryptoStrategySetup(
        strategy_name=req.strategy,
        symbol=clean_sym,
        direction="SHORT" if is_short else "LONG",
        timeframe=req.timeframe,  # type: ignore
        is_scalp=req.timeframe in ("1m", "3m"),
        spot_price=spot_d,
        entry_trigger=trig_d,
        raw_structural_stop=sl_d,
        structural_target_candidates=[t1_d, t2_d],
        atr_val=Decimal("80.0"),
        confidence=req.confidence or 80.0,
    )
    risk_res = crypto_risk_engine.evaluate(setup)
    if not risk_res.accepted:
        raise HTTPException(status_code=400, detail=f"Risk envelope rejection: {risk_res.rejection_reason}")

    # 3. Create and Register FSM Instance
    instance = CryptoSignalInstance(
        symbol=clean_sym,
        asset="BTC" if "BTC" in clean_sym else "ETH",
        direction="SHORT" if is_short else "LONG",
        strategy=req.strategy,
        strategy_name=f"Manual {req.strategy}",
        timeframe=req.timeframe,
        is_scalp=req.timeframe in ("1m", "3m"),
        spot_price=spot_d,
        trigger=risk_res.entry_price,
        stop_loss=risk_res.stop_loss,
        target_1=risk_res.target_1,
        target_2=risk_res.target_2,
        risk_points=Decimal(str(risk_res.risk_points)),
        risk_reward_t1=risk_res.risk_reward_t1,
        risk_reward_t2=risk_res.risk_reward_t2,
        confidence=req.confidence or 80.0,
        confluence_breakdown={"technical": 80.0, "mtf": 75.0, "derivatives": 75.0, "regime": 80.0, "sentiment": 75.0},
        rationale=req.rationale or [f"Manual {req.strategy} setup on {clean_sym}"],
        ttl_seconds=risk_res.trigger_ttl_seconds,
        time_stop_seconds=risk_res.active_time_stop_seconds,
        runner_ttl_seconds=risk_res.runner_ttl_seconds,
        quantity=risk_res.quantity,
        notional_usd=risk_res.notional_usd,
        max_usd_loss=risk_res.max_usd_loss,
        fsm_state="ARMED",
    )
    crypto_signal_fsm.register(instance)

    # Broadcast via Crypto SSE Hub
    await crypto_sse_hub.broadcast("signal_created", instance.model_dump(), priority="P0")

    return {
        "success": True,
        "signal_id": instance.signal_id,
        "symbol": instance.symbol,
        "state": instance.fsm_state,
        "trigger": float(instance.trigger),
        "stop_loss": float(instance.stop_loss),
        "target_1": float(instance.target_1),
        "target_2": float(instance.target_2),
        "quantity": instance.quantity,
        "max_usd_loss": instance.max_usd_loss,
        "created_at_str": instance.created_at_str,
    }


# ── 5. SIGNAL DEEP DIVE & DELETION ────────────────────────────────────

@router.get("/{signal_id}/deep-dive")
@router.get("/deep-dive/{signal_id}")
async def get_crypto_signal_deep_dive(signal_id: str):
    """
    Comprehensive technical dossier for a single crypto signal.
    """
    sig = crypto_signal_fsm.get(signal_id)
    if not sig:
        raise HTTPException(status_code=404, detail="Crypto signal not found in active FSM.")

    recon = crypto_fill_reconciler.get_record(signal_id)

    return {
        "signal": sig.model_dump(),
        "reconciliation": recon.model_dump() if recon else None,
        "fsm_history": [h.model_dump() for h in sig.state_history],
        "two_clock_lifecycle": {
            "ttl_seconds": sig.ttl_seconds,
            "ttl_remaining_seconds": sig.ttl_remaining_seconds(),
            "time_stop_seconds": sig.time_stop_seconds,
            "runner_ttl_seconds": sig.runner_ttl_seconds,
        },
        "timestamp_ms": int(time.time() * 1000),
    }


@router.delete("/{signal_id}")
async def delete_crypto_signal(signal_id: str):
    """Delete crypto signal from in-memory FSM and scanner cache, then broadcast deletion event."""
    deleted_fsm = crypto_signal_fsm.delete(signal_id)
    deleted_scanner = crypto_scalp_scanner._active_signals.pop(signal_id, None) is not None

    if not deleted_fsm and not deleted_scanner:
        raise HTTPException(status_code=404, detail="Signal not found.")

    await crypto_sse_hub.broadcast("signal_deleted", {"signal_id": signal_id}, priority="P0")
    return {"status": "success", "signal_id": signal_id}


# ── 6. HISTORICAL DATA, PERFORMANCE & LEDGER ──────────────────────────

@router.get("/history", response_model=list[CryptoScalpSignal])
async def get_crypto_scalp_history(
    symbol: Optional[str] = Query(None, description="Optional symbol filter"),
    limit: int = Query(50, ge=1, le=200, description="Max signals to return"),
):
    """Retrieve historical persisted scalp signals from Supabase PostgreSQL."""
    try:
        signals = await fetch_persisted_scalp_signals(limit=limit, symbol=symbol)
        return signals
    except Exception as e:
        logger.error("get_crypto_scalp_history_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch signal history: {str(e)}")


@router.get("/diagnostics", response_model=CryptoScalpDiagnostics)
async def get_crypto_scalp_diagnostics():
    """Inspect scanner health, worker execution status, and data availability."""
    try:
        diag = crypto_scalp_scanner.get_diagnostics()
        diag.worker_running = crypto_scalp_worker.is_running
        diag.scan_interval_seconds = crypto_scalp_worker.interval_seconds
        diag.telegram_enabled = settings.crypto_scalp_telegram_enabled
        return diag
    except Exception as e:
        logger.error("get_crypto_scalp_diagnostics_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Diagnostics failed: {str(e)}")


@router.patch("/config", response_model=CryptoScalpConfig)
async def update_crypto_scalp_config(
    config: CryptoScalpConfig = Body(...),
):
    """Dynamically update the crypto scalp scan interval and Telegram notifications toggle."""
    try:
        crypto_scalp_worker.set_interval(config.scan_interval_seconds)
        settings.crypto_scalp_telegram_enabled = config.telegram_enabled
        return CryptoScalpConfig(
            scan_interval_seconds=crypto_scalp_worker.interval_seconds,
            telegram_enabled=settings.crypto_scalp_telegram_enabled,
        )
    except Exception as e:
        logger.error("update_crypto_scalp_config_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Config update failed: {str(e)}")


@router.get("/performance", response_model=CryptoScalpPerformanceMetrics)
async def get_crypto_scalp_performance():
    """Retrieve quantitative performance attribution metrics across all scalp trades."""
    try:
        records = await fetch_execution_records(limit=200)
        metrics = performance_engine.calculate_metrics(records)
        return metrics
    except Exception as e:
        logger.error("get_crypto_scalp_performance_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to calculate performance: {str(e)}")


@router.get("/ledger", response_model=list[CryptoScalpExecutionRecord])
async def get_crypto_scalp_ledger(
    symbol: Optional[str] = Query(None, description="Filter by symbol (e.g. BTCUSDT, ETHUSDT)"),
    state: Optional[str] = Query(None, description="Filter by position state: ACTIVE, PARTIALLY_CLOSED, CLOSED"),
    limit: int = Query(50, ge=1, le=200, description="Max trade records to return"),
):
    """Retrieve the chronological execution ledger of paper trades with detailed P&L and R-multiples."""
    try:
        pos_state = None
        if state:
            try:
                pos_state = CryptoScalpPositionState(state.upper().strip())
            except ValueError:
                pass

        records = await fetch_execution_records(limit=limit, symbol=symbol, state=pos_state)
        return records
    except Exception as e:
        logger.error("get_crypto_scalp_ledger_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch execution ledger: {str(e)}")


@router.get("/ledger/{trade_id}", response_model=CryptoScalpExecutionRecord)
async def get_crypto_scalp_trade_detail(trade_id: str):
    """Retrieve full execution record and granular audit event timeline for a specific trade."""
    try:
        trade = await fetch_execution_record_by_id(trade_id)
        if not trade:
            raise HTTPException(status_code=404, detail=f"Trade {trade_id} not found")
        return trade
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_crypto_scalp_trade_detail_failed", trade_id=trade_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to fetch trade details: {str(e)}")


@router.delete("/ledger/{trade_id}")
async def delete_crypto_scalp_trade(trade_id: str):
    """Delete a trade execution record and its events from the ledger."""
    try:
        from app.crypto_scalp.persistence import delete_execution_record
        await delete_execution_record(trade_id)
        return {"status": "success", "trade_id": trade_id}
    except Exception as e:
        logger.error("delete_crypto_scalp_trade_failed", trade_id=trade_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to delete trade {trade_id}: {str(e)}")
