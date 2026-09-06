"""
Crypto Scalping API Endpoints
Provides real-time 1m/5m scalping signals, manual triggers, persistence queries,
diagnostics, and configurable scanning cadence.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query, Body, HTTPException
import structlog

from app.core.config import settings
from app.crypto_scalp.scanner import crypto_scalp_scanner
from app.crypto_scalp.worker import crypto_scalp_worker
from app.crypto_scalp.persistence import (
    fetch_persisted_scalp_signals,
    fetch_execution_records,
    fetch_execution_record_by_id,
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
)

logger = structlog.get_logger()

router = APIRouter(prefix="/api/v1/crypto/scalp-signals", tags=["crypto-scalp"])


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


@router.post("/scan", response_model=CryptoScalpSignalsResponse)
async def trigger_manual_scalp_scan():
    """Force an immediate fresh scalp scan across all crypto pairs."""
    try:
        response = await crypto_scalp_scanner.scan_all(force_refresh=True)
        return response
    except Exception as e:
        logger.error("manual_crypto_scalp_scan_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Manual scan failed: {str(e)}")


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
    """
    Dynamically update the crypto scalp scan interval and Telegram notifications toggle.
    """
    try:
        crypto_scalp_worker.set_interval(config.scan_interval_seconds)
        settings.crypto_scalp_telegram_enabled = config.telegram_enabled
        logger.info(
            "crypto_scalp_config_updated",
            scan_interval_seconds=config.scan_interval_seconds,
            telegram_enabled=config.telegram_enabled,
        )
        return CryptoScalpConfig(
            scan_interval_seconds=crypto_scalp_worker.interval_seconds,
            telegram_enabled=settings.crypto_scalp_telegram_enabled,
        )
    except Exception as e:
        logger.error("update_crypto_scalp_config_failed", error=str(e))
        raise HTTPException(status_code=500, detail=f"Config update failed: {str(e)}")


@router.get("/performance", response_model=CryptoScalpPerformanceMetrics)
async def get_crypto_scalp_performance():
    """
    Retrieve quantitative performance attribution metrics across all scalp trades:
    empirical win rate %, profit factor, expectancy R, execution drag, strategy & asset stats.
    """
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
    """
    Retrieve the chronological execution ledger of paper trades with detailed P&L and R-multiples.
    """
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
    """
    Retrieve full execution record and granular audit event timeline for a specific trade.
    """
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

