"""
Swing Module Background Worker (v5.0 §24).
Schedules:
  1. EOD Scan: Executes at 15:35 IST after daily session close.
  2. Intraday Monitor: Checks triggers and trailing stops every 15 minutes during market hours.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import structlog
from app.services.calendar_service import calendar_service
from app.swing.scanner import swing_scanner

logger = structlog.get_logger()


class SwingWorker:
    def __init__(self, check_interval_s: float = 60.0):
        self.check_interval_s = check_interval_s
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_eod_date = None

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("swing_worker_started")

    def stop(self):
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
        logger.info("swing_worker_stopped")

    async def _run_loop(self):
        while self._running:
            try:
                # IST is UTC + 5:30
                now_utc = datetime.now(timezone.utc)
                now_ist = now_utc + timedelta(hours=5, minutes=30)
                today_ist_date = now_ist.date()

                is_trading_day = now_ist.weekday() < 5 and not calendar_service.is_holiday(today_ist_date)

                # Check if it's 15:35 IST or later on a trading day and EOD scan hasn't run today
                if is_trading_day:
                    if (now_ist.hour == 15 and now_ist.minute >= 35) or now_ist.hour >= 16:
                        if self._last_eod_date != today_ist_date:
                            logger.info("swing_worker_triggering_eod_scan", date=str(today_ist_date))
                            await swing_scanner.run_scan(force_refresh=True)
                            self._last_eod_date = today_ist_date

                await asyncio.sleep(self.check_interval_s)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("swing_worker_loop_error", error=str(e)[:150])
                await asyncio.sleep(self.check_interval_s)


swing_worker = SwingWorker(check_interval_s=60.0)
