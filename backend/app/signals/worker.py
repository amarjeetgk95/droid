"""
Automated Dual-Cadence Signal Engine & High-Frequency Outcome Worker (Version 6.0)

Architecture:
  1. Priority 1: Open-Position Risk Management Loop (3-second cadence, 2500ms budget).
     - Dedicated exclusively to open-risk management, stops, ratchets, and staged exits.
     - NEVER creates or scans new candidates.
     - Cycle-overrun protection with latency telemetry.
  2. Priority 2: Dual-Cadence Candidate Scanner Loop.
     - Fast Scalp Desk (1M): Scans every 10 seconds on confirmed candle closes.
     - Core Intraday Desk (5M): Scans every 30 seconds on 5M candles.
"""
from __future__ import annotations

import asyncio
import time
from decimal import Decimal
import structlog

from app.signals.contract_resolver import APPROVED_UNDERLYINGS
from app.signals.scanner import scanner_engine
from app.signals.outcome_tracker import outcome_tracker
from app.services.market_service import MarketService

logger = structlog.get_logger()


class AutomatedSignalWorker:
    """
    Decoupled dual-cadence worker:
      - Risk Management Loop (3s, budget: 2500ms)
      - Scalp Scanner Loop (10s)
      - Intraday Scanner Loop (30s)
    """

    def __init__(
        self,
        risk_interval_seconds: float = 3.0,
        scalp_scan_interval_seconds: float = 10.0,
        intraday_scan_interval_seconds: float = 30.0,
        max_risk_cycle_budget_ms: float = 2500.0,
    ):
        self._risk_interval = risk_interval_seconds
        self._scalp_interval = scalp_scan_interval_seconds
        self._intraday_interval = intraday_scan_interval_seconds
        self._budget_ms = max_risk_cycle_budget_ms

        self._running = False
        self._risk_task: asyncio.Task | None = None
        self._scanner_task: asyncio.Task | None = None
        self._market_svc = MarketService()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._risk_task = asyncio.create_task(self._run_position_risk_loop())
        self._scanner_task = asyncio.create_task(self._run_scanner_loop())
        logger.info(
            "automated_signal_worker_started",
            risk_interval=self._risk_interval,
            scalp_interval=self._scalp_interval,
            intraday_interval=self._intraday_interval,
        )

    async def stop(self) -> None:
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
        logger.info("automated_signal_worker_stopped")

    async def _run_position_risk_loop(self) -> None:
        """
        Dedicated 3-second open-position risk management loop (§14).
        Must complete within 2500ms budget.
        """
        while self._running:
            cycle_start = time.perf_counter()
            try:
                # Iterate approved instruments and manage open risk
                for u in list(APPROVED_UNDERLYINGS):
                    try:
                        quote = await self._market_svc.get_quote(u)
                        if quote and getattr(quote, "ltp", None) is not None:
                            curr_p = Decimal(str(quote.ltp))
                            # Process price updates (triggers, ratchets, staged exits, time stops)
                            await outcome_tracker.process_price_update_async(u, curr_p)

                            # Update live MTM in Signal Audit Ledger
                            from app.signals.audit_ledger import signal_audit_ledger
                            from app.signals.sse import signal_sse_hub
                            updated_recs = signal_audit_ledger.update_live_quote(u, float(curr_p))
                            if updated_recs:
                                await signal_sse_hub.broadcast(
                                    "audit_pnl_update",
                                    {
                                        "underlying": u,
                                        "ltp": float(curr_p),
                                        "summary": signal_audit_ledger.get_summary_metrics(),
                                    },
                                    priority="P1",
                                )
                    except Exception as pe:
                        logger.debug("worker_risk_tick_err", underlying=u, error=str(pe))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("risk_management_cycle_error", error=str(e))

            cycle_duration_ms = (time.perf_counter() - cycle_start) * 1000.0
            if cycle_duration_ms > self._budget_ms:
                logger.warning(
                    "risk_management_cycle_overrun",
                    duration_ms=round(cycle_duration_ms, 2),
                    budget_ms=self._budget_ms,
                )

            # Sleep remaining budget
            sleep_sec = max(0.1, self._risk_interval - (cycle_duration_ms / 1000.0))
            try:
                await asyncio.sleep(sleep_sec)
            except asyncio.CancelledError:
                break

    async def _run_scanner_loop(self) -> None:
        """
        Dual-cadence candidate scanning loop:
          - Scalp Desk: every 10 seconds
          - Intraday Desk: every 30 seconds
        """
        last_scalp_ts = 0.0
        last_intraday_ts = 0.0

        while self._running:
            try:
                now = time.time()

                # 1. Fast Scalp Scanning (1M)
                if now - last_scalp_ts >= self._scalp_interval:
                    last_scalp_ts = now
                    try:
                        await scanner_engine.scan_scalp()
                    except Exception as se:
                        logger.debug("scalp_scanner_error", error=str(se))

                # 2. Core Intraday Scanning (5M)
                if now - last_intraday_ts >= self._intraday_interval:
                    last_intraday_ts = now
                    try:
                        await scanner_engine.scan_intraday()
                    except Exception as ie:
                        logger.debug("intraday_scanner_error", error=str(ie))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("scanner_loop_error", error=str(e))

            try:
                await asyncio.sleep(2.0)
            except asyncio.CancelledError:
                break


automated_signal_worker = AutomatedSignalWorker()

