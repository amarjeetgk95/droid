"""
Automated Dual-Cadence Crypto Signal Engine & High-Frequency Outcome Worker (Version 6.0)
Architecture:
  1. Priority 1: Open-Position Risk Management Loop (2.5-second cadence, 1500ms budget).
     - Dedicated exclusively to open-risk management, stops, +0.8R ratchets, staged exits, and time stops.
     - NEVER creates or scans new candidates.
     - Cycle-overrun protection with latency telemetry.
  2. Priority 2: Dual-Cadence Candidate Scanner Loop (24/7 continuous).
     - Fast Scalp Desk (1M): Scans every 10 seconds.
     - Core Intraday Desk (5M): Scans every 30 seconds.
"""
from __future__ import annotations

import asyncio
import time
import structlog
from app.core.config import settings

logger = structlog.get_logger()

MONITORED_CRYPTO_SYMBOLS = ["BTCUSDT", "ETHUSDT"]


class CryptoScalpWorker:
    """
    Decoupled dual-cadence 24/7 worker:
      - Risk Management Loop (2.5s cadence, budget: 1500ms)
      - Scalp Scanner Loop (10s cadence, 1M)
      - Intraday Scanner Loop (30s cadence, 5M)
    """

    def __init__(
        self,
        risk_interval_seconds: float = 2.5,
        scalp_scan_interval_seconds: float = 10.0,
        intraday_scan_interval_seconds: float = 30.0,
        max_risk_cycle_budget_ms: float = 1500.0,
    ):
        self._risk_interval = risk_interval_seconds
        self._scalp_interval = scalp_scan_interval_seconds
        self._intraday_interval = intraday_scan_interval_seconds
        self._budget_ms = max_risk_cycle_budget_ms

        self._running = False
        self._risk_task: asyncio.Task | None = None
        self._scanner_task: asyncio.Task | None = None
        self._interval_seconds: int = int(scalp_scan_interval_seconds)

    @property
    def is_running(self) -> bool:
        return self._running and self._risk_task is not None and not self._risk_task.done()

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def set_interval(self, seconds: int) -> None:
        """Update scan interval dynamically."""
        clamped = max(10, min(300, seconds))
        self._interval_seconds = clamped
        self._scalp_interval = float(clamped)
        settings.crypto_scalp_scan_interval_seconds = clamped
        logger.info("crypto_scalp_interval_updated", interval_seconds=clamped)

    async def start(self) -> None:
        """Start the decoupled background risk and scanning tasks."""
        if self._running and self._risk_task and not self._risk_task.done():
            logger.debug("crypto_scalp_worker_already_running")
            return

        self._running = True
        self._risk_task = asyncio.create_task(self._run_position_risk_loop(), name="crypto_risk_loop")
        self._scanner_task = asyncio.create_task(self._run_scanner_loop(), name="crypto_scanner_loop")
        logger.info(
            "crypto_scalp_worker_started",
            risk_interval=self._risk_interval,
            scalp_interval=self._scalp_interval,
            intraday_interval=self._intraday_interval,
            telegram_enabled=settings.crypto_scalp_telegram_enabled,
        )

    async def stop(self) -> None:
        """Gracefully terminate background tasks."""
        self._running = False
        for t in (self._risk_task, self._scanner_task):
            if t:
                t.cancel()
                try:
                    await t
                except (asyncio.CancelledError, Exception):
                    pass
        self._risk_task = None
        self._scanner_task = None
        logger.info("crypto_scalp_worker_stopped")

    async def _run_position_risk_loop(self) -> None:
        """
        Dedicated 2.5-second open-position risk management loop.
        Processes ticks, +0.8R breakeven ratchets, staged exits, and time stops.
        """
        from app.crypto_scalp.outcome_tracker import crypto_scalp_outcome_tracker
        from app.crypto_scalp.persistence import restore_crypto_signals_state_local
        from app.services.binance_service import binance_service

        await asyncio.sleep(2.0)

        # Startup recovery of state from database and local cache
        try:
            await crypto_scalp_outcome_tracker.recover_active_positions()
            restore_crypto_signals_state_local()
        except Exception as e:
            logger.warning("crypto_worker_startup_recovery_failed", error=str(e)[:200])

        while self._running:
            cycle_start = time.perf_counter()
            try:
                for sym in MONITORED_CRYPTO_SYMBOLS:
                    try:
                        candles = await binance_service.get_candles(sym, "1m", limit=2)
                        ob = await binance_service.get_order_book(sym, limit=5)
                        if candles:
                            last_c = candles[-1]
                            spread = (ob.best_ask - ob.best_bid) if ob and ob.best_ask and ob.best_bid else 0.0
                            await crypto_scalp_outcome_tracker.process_tick(
                                symbol=sym,
                                current_price=last_c.close,
                                high=last_c.high,
                                low=last_c.low,
                                spread=spread,
                            )
                    except Exception as tick_err:
                        logger.debug("crypto_risk_tick_eval_failed", symbol=sym, error=str(tick_err)[:150])
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("crypto_risk_loop_error", error=str(e)[:200])

            cycle_duration_ms = (time.perf_counter() - cycle_start) * 1000.0
            if cycle_duration_ms > self._budget_ms:
                logger.warning(
                    "crypto_risk_cycle_overrun",
                    duration_ms=round(cycle_duration_ms, 2),
                    budget_ms=self._budget_ms,
                )

            sleep_sec = max(0.1, self._risk_interval - (cycle_duration_ms / 1000.0))
            try:
                await asyncio.sleep(sleep_sec)
            except asyncio.CancelledError:
                break

    async def _run_scanner_loop(self) -> None:
        """
        Dual-cadence candidate scanning loop (24/7 continuous):
          - Fast Scalp (1M): every 10 seconds.
          - Core Intraday (5M): every 30 seconds.
        """
        from app.crypto_scalp.scanner import crypto_scalp_scanner

        await asyncio.sleep(4.0)
        last_scalp_ts = 0.0
        last_intraday_ts = 0.0

        while self._running:
            try:
                now = time.time()

                # 1. Fast Scalp Scanning (1M)
                if (now - last_scalp_ts) >= self._scalp_interval:
                    last_scalp_ts = now
                    try:
                        await crypto_scalp_scanner.scan_scalp()
                    except Exception as se:
                        logger.debug("crypto_scalp_scan_error", error=str(se)[:150])

                # 2. Core Intraday Scanning (5M)
                if (now - last_intraday_ts) >= self._intraday_interval:
                    last_intraday_ts = now
                    try:
                        await crypto_scalp_scanner.scan_intraday()
                    except Exception as ie:
                        logger.debug("crypto_intraday_scan_error", error=str(ie)[:150])

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("crypto_scanner_loop_error", error=str(e)[:200])

            try:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break


crypto_scalp_worker = CryptoScalpWorker()
