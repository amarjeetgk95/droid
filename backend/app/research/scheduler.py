"""Hourly forecast data-collection scheduler (P3 follow-up).

Runs shadow recording + research settlement once per hour so Cycle-1
evidence accumulates automatically once FYERS is re-authed. Disabled by
default (``FORECAST_SCHEDULER_ENABLED=on`` to enable); market-closed hours
are graceful no-ops via :mod:`app.research.shadow_scheduler`.

Stdlib + repo modules only. Importing this module has no side effects.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

FLAG = "FORECAST_SCHEDULER_ENABLED"
DEFAULT_INSTRUMENTS: List[str] = ["NIFTY 50", "BANKNIFTY"]

_task: Optional[asyncio.Task] = None


def scheduler_enabled() -> bool:
    """True only when explicitly enabled (default off — safe for dev/CI)."""
    return str(os.getenv(FLAG, "off")).strip().lower() in ("1", "true", "on", "yes")


def seconds_until_next_run(now_utc: Optional[datetime] = None) -> float:
    """Seconds until next :05 past the hour IST (Asia/Kolkata = UTC+5:30).

    Pure — unit-testable. IST has no DST so a fixed offset is correct.
    """
    now = now_utc or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    now_ist = now + ist_offset
    # Next hour at minute 5 IST.
    nxt = now_ist.replace(minute=5, second=0, microsecond=0)
    if nxt <= now_ist:
        nxt = nxt + timedelta(hours=1)
    return max(1.0, (nxt - now_ist).total_seconds())


async def run_once(
    instruments: Optional[List[str]] = None,
    session: Any = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Execute one collection tick: shadow record + research settlement.

    Never raises — per-stage failures are captured in the summary. When no
    DB session factory is available, stages run with ``session=None``
    (memory-only recording) and report it.
    """
    from app.research.shadow_scheduler import run_hourly_shadow

    summary: Dict[str, Any] = {"started_at": (now_utc or datetime.now(timezone.utc)).isoformat()}
    sess = session
    own_session = False
    if sess is None:
        try:
            from app.core.database import get_async_session_factory

            factory = get_async_session_factory()
            if factory is not None:
                sess = factory()
                own_session = True
        except Exception as e:
            logger.warning("forecast_scheduler_no_session", error=str(e)[:200])

    try:
        try:
            summary["shadow"] = await run_hourly_shadow(
                instruments=instruments or list(DEFAULT_INSTRUMENTS),
                session=sess,
                now_utc=now_utc,
            )
        except Exception as e:
            logger.warning("forecast_scheduler_shadow_failed", error=str(e)[:200])
            summary["shadow"] = {"error": str(e)[:200]}

        try:
            from app.research.settlement import settle_due_research

            if sess is not None:
                summary["settlement"] = await settle_due_research(sess, limit=100, now_utc=now_utc)
            else:
                summary["settlement"] = {"skipped": "no-session"}
        except Exception as e:
            logger.warning("forecast_scheduler_settle_failed", error=str(e)[:200])
            summary["settlement"] = {"error": str(e)[:200]}
    finally:
        if own_session:
            try:
                await sess.close()
            except Exception:
                pass
    return summary


async def _loop() -> None:
    try:
        while True:
            delay = seconds_until_next_run()
            await asyncio.sleep(delay)
            try:
                summary = await run_once()
                logger.info(
                    "forecast_scheduler_tick",
                    shadow_ran=len((summary.get("shadow") or {}).get("ran", [])),
                    shadow_skipped=len((summary.get("shadow") or {}).get("skipped", {})),
                )
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("forecast_scheduler_tick_failed", error=str(e)[:200])
    except asyncio.CancelledError:
        pass


async def start_forecast_scheduler() -> bool:
    """Start the hourly loop. Returns True if started, False if disabled."""
    global _task
    if not scheduler_enabled():
        logger.info("forecast_scheduler_disabled", flag=FLAG)
        return False
    if _task is not None and not _task.done():
        return True
    _task = asyncio.create_task(_loop(), name="forecast-scheduler")
    logger.info("forecast_scheduler_started")
    return True


async def stop_forecast_scheduler() -> None:
    """Stop the hourly loop (no-op when not running). Never raises."""
    global _task
    task, _task = _task, None
    if task is None:
        return
    try:
        task.cancel()
        await task
    except Exception:
        pass
