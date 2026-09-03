"""
Automated Signal Engine & Outcome Worker
Runs in the background to:
  1. Continuously evaluate live market quotes for NIFTY, BANKNIFTY, SENSEX
  2. Detect quantitative setups via scanner_engine across 5 strategies
  3. Track active signal triggers & confirmations in real time
  4. Auto-execute confirmed signals into Paper Trading
  5. Auto-square off positions on Target/Stop hit with actual P&L audit
  6. Dispatch automated Telegram notifications
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
    def __init__(self, scan_interval_seconds: float = 15.0, price_poll_interval_seconds: float = 3.0):
        self._scan_interval = scan_interval_seconds
        self._price_poll_interval = price_poll_interval_seconds
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_scan_ts: float = 0.0
        self._market_svc = MarketService()

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("automated_signal_worker_started", scan_interval=self._scan_interval)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("automated_signal_worker_stopped")

    async def _run_loop(self) -> None:
        while self._running:
            try:
                now = time.time()

                # 1. Update active signals with live price & process triggers/exits
                for u in list(APPROVED_UNDERLYINGS):
                    try:
                        quote = await self._market_svc.get_quote(u)
                        if quote and getattr(quote, "ltp", None) is not None:
                            curr_p = Decimal(str(quote.ltp))
                            # Process async updates (triggers -> paper execution, targets/stops -> square-off + P&L)
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
                        logger.debug("worker_price_update_err", underlying=u, error=str(pe))

                # 2. Periodic multi-strategy scanning for new setups
                if now - self._last_scan_ts >= self._scan_interval:
                    self._last_scan_ts = now
                    try:
                        await scanner_engine.scan_all()
                    except Exception as se:
                        logger.debug("worker_scan_all_err", error=str(se))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("automated_signal_worker_loop_error", error=str(e))

            try:
                await asyncio.sleep(self._price_poll_interval)
            except asyncio.CancelledError:
                break


automated_signal_worker = AutomatedSignalWorker()
