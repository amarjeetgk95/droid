"""
Crypto Scalp Scanner Background Worker
Runs autonomous 24/7 background scanning at a configurable interval.
"""
from __future__ import annotations

import asyncio
import structlog
from app.core.config import settings

logger = structlog.get_logger()


class CryptoScalpWorker:
    """Autonomous background worker executing periodic scalp scans."""

    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running: bool = False
        self._interval_seconds: int = settings.crypto_scalp_scan_interval_seconds

    @property
    def is_running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    @property
    def interval_seconds(self) -> int:
        return self._interval_seconds

    def set_interval(self, seconds: int) -> None:
        """Update scan interval dynamically."""
        clamped = max(10, min(300, seconds))
        self._interval_seconds = clamped
        settings.crypto_scalp_scan_interval_seconds = clamped
        logger.info("crypto_scalp_interval_updated", interval_seconds=clamped)

    async def start(self) -> None:
        """Start the background scanning loop."""
        if self._running and self._task and not self._task.done():
            logger.debug("crypto_scalp_worker_already_running")
            return

        self._running = True
        self._task = asyncio.create_task(self._loop(), name="crypto_scalp_worker_loop")
        logger.info(
            "crypto_scalp_worker_started",
            interval_seconds=self._interval_seconds,
            telegram_enabled=settings.crypto_scalp_telegram_enabled,
        )

    async def stop(self) -> None:
        """Gracefully terminate background scanning loop."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        logger.info("crypto_scalp_worker_stopped")

    async def _loop(self) -> None:
        """Main execution loop for crypto scalp scanning."""
        from app.crypto_scalp.scanner import crypto_scalp_scanner

        # Initial delay on startup so Binance service and other systems initialize
        await asyncio.sleep(3.0)

        while self._running:
            try:
                await crypto_scalp_scanner.scan_all(force_refresh=True)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("crypto_scalp_worker_cycle_failed", error=str(e)[:200])

            try:
                await asyncio.sleep(self._interval_seconds)
            except asyncio.CancelledError:
                break


crypto_scalp_worker = CryptoScalpWorker()
