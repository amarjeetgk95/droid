"""Nightly institutional jobs: history ingest + drift check (disabled by default).

Enable with FLOW_SCHEDULER_ENABLED=on. Runs daily ~19:30 IST (after T+1 18:00
availability + NSE provisional/final cycle):
  1. ingest history-full proxy -> data/fii_dii_history.json (best-effort network)
  2. drift check -> data/institutional_degraded.flag
Never raises; all failures are logged and reported in the summary.
Stdlib + repo modules only. Importing has no side effects.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from typing import Any
import structlog

from app.signals.safety.clocks import to_ist

logger = structlog.get_logger(__name__)

FLAG = "FLOW_SCHEDULER_ENABLED"
_task = None


def enabled() -> bool:
    return str(os.getenv(FLAG, "off")).strip().lower() in ("1", "true", "on", "yes")


async def run_once() -> dict[str, Any]:
    out: dict[str, Any] = {"at": datetime.now(timezone.utc).isoformat(), "ingest": None, "drift": None}
    backend = __import__("pathlib").Path(__file__).resolve().parents[1]
    try:
        p = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "scripts/ingest_fii_dii_history.py", "--out", "data/fii_dii_history.json"],
            cwd=str(backend), capture_output=True, text=True, timeout=120,
        )
        out["ingest"] = {"rc": p.returncode, "tail": (p.stdout or "")[-300:] + (p.stderr or "")[-300:]}
    except Exception as e:
        out["ingest"] = {"rc": -1, "error": str(e)[:200]}
        logger.warning("flow_ingest_failed", error=str(e))
    try:
        from app.institutional.drift import check_drift

        drift = await asyncio.to_thread(check_drift)
        out["drift"] = drift
        if isinstance(drift, dict) and drift.get("degraded"):
            logger.warning("institutional_drift_degraded", reason=drift.get("reason"))
            # Best-effort operator alert via Telegram queue (never raises).
            try:
                from app.institutional.telegram_notifications import (
                    SignalEvent,
                    telegram_notification_queue,
                )

                ev = SignalEvent(
                    event_type="RISK_ALERT",
                    signal_id=f"drift-{drift.get('at', 'now')}",
                    instrument="NIFTY",
                    candle_timeframe="1D",
                    setup_type="INSTITUTIONAL_DRIFT",
                    direction="NEUTRAL",
                    status="DEGRADED",
                    trigger_level=0.0,
                    current_price=0.0,
                )
                try:
                    telegram_notification_queue.put_nowait(ev)
                except Exception:
                    pass
            except Exception:
                pass
    except Exception as e:
        out["drift"] = {"error": str(e)[:200]}
    return out


async def _loop() -> None:
    while True:
        try:
            now = datetime.now(timezone.utc)
            ist = to_ist(now)
            nxt = ist.replace(hour=19, minute=30, second=0, microsecond=0)
            if nxt <= ist:
                nxt += timedelta(days=1)
            await asyncio.sleep(max(60.0, (nxt - ist).total_seconds()))
            if enabled():
                await run_once()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning("flow_scheduler_tick_failed", error=str(e))
            await asyncio.sleep(3600)


def start() -> None:
    global _task
    if _task is None and enabled():
        try:
            _task = asyncio.get_running_loop().create_task(_loop())
        except RuntimeError:
            pass
