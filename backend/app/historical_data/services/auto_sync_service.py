"""Automated End-of-Day (EOD) Historical Ingestion & Startup Catch-Up Service.

Responsible for:
1. Scheduling post-market daily delta ingestion at 16:30 IST on trading days.
2. Checking for missing trading days on backend startup (desktop/laptop reboot resilience).
3. Incrementally appending missing 1-minute bars to existing Parquet datasets.
4. Triggering automatic higher-timeframe resampled derivation (5m, 15m, 30m, 1h, 1D).
"""

from __future__ import annotations
import asyncio
import os
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Dict, Any, List, Tuple
import structlog

from app.historical_data.calendar.india import indian_calendar, IST_TZ
from app.historical_data.storage.db_repository import db_repo
from app.historical_data.services.download_service import download_service
from app.historical_data.models.job import HistoricalDownloadJob

logger = structlog.get_logger(__name__)

EOD_SYNC_TIME = time(16, 30)  # 4:30 PM IST post-market closing & settlement


class HistoricalAutoSyncService:
    """Manages scheduled daily historical data ingestion and missed session catch-up."""

    def __init__(self):
        env_val = os.getenv("HISTORICAL_AUTO_SYNC_ENABLED", "true").strip().lower()
        self.enabled: bool = env_val in ("1", "true", "yes", "on")
        self.tracked_symbols: List[str] = ["SENSEX", "NIFTY", "BANKNIFTY"]
        self.is_running: bool = False
        self.last_sync_at: Optional[datetime] = None
        self.last_sync_status: str = "IDLE"
        self.last_sync_summary: Dict[str, Any] = {}
        self._worker_task: Optional[asyncio.Task] = None

    def get_last_completed_trading_day(self, now_dt: Optional[datetime] = None) -> Optional[date]:
        """Find the most recent trading date that has completed its session and settlement."""
        if now_dt is None:
            now_dt = datetime.now(timezone.utc)
        ist_now = now_dt.astimezone(IST_TZ)

        # If today is a trading day and it's past 16:30 IST, today is completed
        if ist_now.time() >= EOD_SYNC_TIME and indian_calendar.is_trading_day(ist_now.date()):
            return ist_now.date()

        # Otherwise, search backwards for the previous trading day
        curr = ist_now.date() - timedelta(days=1)
        for _ in range(14):
            if indian_calendar.is_trading_day(curr):
                return curr
            curr -= timedelta(days=1)

        return None

    def get_next_scheduled_run_ist(self, now_dt: Optional[datetime] = None) -> datetime:
        """Calculate the next 16:30 IST scheduled run time on a trading day."""
        if now_dt is None:
            now_dt = datetime.now(timezone.utc)
        ist_now = now_dt.astimezone(IST_TZ)

        # If today is a trading day and before 16:30 IST, schedule for today at 16:30 IST
        if ist_now.time() < EOD_SYNC_TIME and indian_calendar.is_trading_day(ist_now.date()):
            return datetime.combine(ist_now.date(), EOD_SYNC_TIME, tzinfo=IST_TZ)

        # Otherwise find next trading day at 16:30 IST
        curr = ist_now.date() + timedelta(days=1)
        while not indian_calendar.is_trading_day(curr):
            curr += timedelta(days=1)

        return datetime.combine(curr, EOD_SYNC_TIME, tzinfo=IST_TZ)

    async def get_active_symbols(self) -> List[str]:
        """Discover all active 1-minute datasets or fallback to default tracked symbols."""
        datasets = await db_repo.list_datasets()
        active_syms = set()
        for d in datasets:
            if d.timeframe.lower() in ("1m", "1", "1min") and d.status in ("READY", "DEGRADED"):
                active_syms.add(d.symbol.upper())

        for default_sym in self.tracked_symbols:
            active_syms.add(default_sym)

        return sorted(list(active_syms))

    async def check_missing_deltas(self) -> Dict[str, Tuple[date, date]]:
        """Identify which symbols have missing trading days up to the last completed session."""
        last_completed = self.get_last_completed_trading_day()
        if not last_completed:
            return {}

        missing_deltas: Dict[str, Tuple[date, date]] = {}
        symbols = await self.get_active_symbols()

        for sym in symbols:
            dataset_id = f"{sym.upper()}_1M"
            ds = await db_repo.get_dataset(dataset_id)
            if not ds or not ds.latest_available_ts:
                continue

            latest_ist = ds.latest_available_ts.astimezone(IST_TZ)
            latest_date = latest_ist.date()

            if latest_date < last_completed:
                # If latest candle was before the final 15:29 candle, include latest_date for repair
                if latest_ist.time() < time(15, 29):
                    start_date = latest_date
                else:
                    start_date = latest_date + timedelta(days=1)

                if start_date <= last_completed:
                    missing_deltas[sym] = (start_date, last_completed)

        return missing_deltas

    async def sync_deltas(self, reason: str = "SCHEDULED_EOD") -> Dict[str, Any]:
        """Execute incremental delta downloads for any symbols behind the completed market session."""
        if self.is_running:
            return {"status": "ALREADY_RUNNING", "message": "Daily auto-sync is currently in progress"}

        self.is_running = True
        self.last_sync_status = "RUNNING"
        summary: Dict[str, Any] = {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "synced": [],
            "errors": [],
        }

        try:
            missing = await self.check_missing_deltas()
            if not missing:
                logger.info("historical_auto_sync_up_to_date", reason=reason)
                summary["status"] = "UP_TO_DATE"
                summary["message"] = "All managed historical datasets are completely up to date"
                self.last_sync_status = "COMPLETED"
                self.last_sync_at = datetime.now(timezone.utc)
                self.last_sync_summary = summary
                return summary

            logger.info("historical_auto_sync_starting", count=len(missing), deltas=str(missing), reason=reason)

            for sym, (st_date, end_date) in missing.items():
                try:
                    job = await download_service.enqueue_download(
                        symbol=sym,
                        timeframe="1m",
                        start_date=st_date,
                        end_date=end_date,
                        force_refresh=False,
                    )
                    summary["synced"].append({
                        "symbol": sym,
                        "timeframe": "1m",
                        "start_date": str(st_date),
                        "end_date": str(end_date),
                        "job_id": job.job_id,
                    })
                except Exception as err:
                    logger.error("historical_auto_sync_symbol_failed", symbol=sym, error=str(err))
                    summary["errors"].append({"symbol": sym, "error": str(err)})

            self.last_sync_at = datetime.now(timezone.utc)
            self.last_sync_status = "COMPLETED" if not summary["errors"] else "PARTIAL"
            summary["status"] = self.last_sync_status
            self.last_sync_summary = summary
            return summary

        except Exception as e:
            logger.error("historical_auto_sync_fatal_error", error=str(e))
            self.last_sync_status = "FAILED"
            summary["status"] = "FAILED"
            summary["error"] = str(e)
            self.last_sync_summary = summary
            return summary

        finally:
            self.is_running = False

    async def _startup_catchup_check(self) -> None:
        """Run a catch-up check after backend boots to recover any sessions missed while offline."""
        try:
            # Short sleep to allow database repository and network to stabilize
            await asyncio.sleep(4.0)
            if not self.enabled:
                return

            missing = await self.check_missing_deltas()
            if missing:
                logger.info("historical_catchup_on_startup_needed", deltas=str(missing))
                await self.sync_deltas(reason="STARTUP_CATCHUP")
            else:
                logger.info("historical_catchup_on_startup_all_datasets_current")
        except Exception as e:
            logger.warning("historical_startup_catchup_failed", error=str(e))

    async def _scheduler_loop(self) -> None:
        """Background loop sleeping until the next 16:30 IST window on a trading day."""
        logger.info("historical_auto_sync_loop_started")
        while True:
            try:
                if not self.enabled:
                    await asyncio.sleep(30.0)
                    continue

                now = datetime.now(timezone.utc)
                ist_now = now.astimezone(IST_TZ)
                next_run = self.get_next_scheduled_run_ist(now)
                sleep_secs = max(5.0, (next_run - ist_now).total_seconds())

                logger.debug(
                    "historical_auto_sync_scheduled_next",
                    next_run=next_run.isoformat(),
                    sleep_minutes=round(sleep_secs / 60.0, 1),
                )

                # Sleep in increments of up to 60s for clean shutdown and dynamic toggling
                while sleep_secs > 0 and self.enabled:
                    to_sleep = min(sleep_secs, 60.0)
                    await asyncio.sleep(to_sleep)
                    ist_now = datetime.now(timezone.utc).astimezone(IST_TZ)
                    sleep_secs = (next_run - ist_now).total_seconds()

                if self.enabled:
                    logger.info("historical_auto_sync_triggering_scheduled_eod")
                    await self.sync_deltas(reason="SCHEDULED_EOD")
                    # Sleep 120s to ensure we don't trigger multiple times in the same minute
                    await asyncio.sleep(120.0)

            except asyncio.CancelledError:
                logger.info("historical_auto_sync_loop_cancelled")
                break
            except Exception as e:
                logger.error("historical_auto_sync_loop_error", error=str(e))
                await asyncio.sleep(60.0)

    def start(self) -> None:
        """Start the background scheduler and trigger startup catch-up."""
        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._scheduler_loop(), name="historical-eod-sync")
            asyncio.create_task(self._startup_catchup_check())
            logger.info("historical_auto_sync_service_started", enabled=self.enabled)

    async def stop(self) -> None:
        """Stop the background scheduler."""
        if self._worker_task and not self._worker_task.done():
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
            logger.info("historical_auto_sync_service_stopped")

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic and scheduling telemetry."""
        next_run = self.get_next_scheduled_run_ist()
        return {
            "enabled": self.enabled,
            "is_running": self.is_running,
            "next_run_ist": next_run.strftime("%Y-%m-%d %H:%M:%S IST"),
            "last_sync_at": self.last_sync_at.isoformat() if self.last_sync_at else None,
            "last_sync_status": self.last_sync_status,
            "last_summary": self.last_sync_summary,
            "tracked_symbols": self.tracked_symbols,
        }


# Global singleton service
auto_sync_service = HistoricalAutoSyncService()
