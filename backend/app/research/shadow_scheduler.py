"""Hourly shadow scheduler hook for 1H forecast v2.3 (P3-1).

Calls :func:`app.research.shadow.run_shadow_pair` once per instrument with
``record=True``. Market-closed hours are a graceful no-op per instrument
(via :func:`app.ml.sessions.classify_window`): the run is skipped, recorded
in the summary, and never raises.

Cron / APScheduler compatible: :func:`run_hourly_shadow` is a plain async
function of ``(instruments)`` returning a JSON-serializable summary, with a
sync wrapper for cron. Importing this module has NO side effects — no
scheduler is created here and nothing is wired into app startup (see the
commented examples at the bottom).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import structlog

logger = structlog.get_logger(__name__)

DEFAULT_SHADOW_INSTRUMENTS: List[str] = ["NIFTY 50", "BANKNIFTY"]

# classify_window reasons that mean "market closed" (graceful skip). Note
# "crosses-session-close" is deliberately ABSENT: the market is still open
# (late-session); the forecast runs and records its UNSETTLEABLE verdict.
_MARKET_CLOSED_MARKERS = (
    "non-trading-day",
    "outside-session",
    "special-session",
)


def _is_market_closed_reason(reason: str) -> bool:
    text = str(reason or "").lower()
    return any(marker in text for marker in _MARKET_CLOSED_MARKERS)


async def run_hourly_shadow(
    instruments: Optional[List[str]] = None,
    horizon: str = "1h",
    forecaster: Any = None,
    session: Any = None,
    now_utc: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Run one shadow pair per instrument; skip gracefully when closed.

    Args:
        instruments: symbols to shadow (default NIFTY 50 + BANKNIFTY).
        horizon: forecast horizon (``"1h"``).
        forecaster: injectable forecaster (tests); None builds the real one
            lazily inside :func:`run_shadow_pair`.
        session: optional AsyncSession for persistence.
        now_utc: trigger clock (defaults to now; explicit in tests).

    Returns:
        Summary ``{"started_at", "horizon", "ran", "skipped", "errors",
        "results"}`` where ``results[instrument]`` is
        ``{"status": "recorded"|"skipped-market-closed"|"classify-failed"|"error",
        "reason"?, "prediction_ids"?}``. Never raises for per-instrument
        failures.
    """
    from app.ml.sessions import classify_window
    from app.research.shadow import run_shadow_pair

    now = now_utc
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)

    symbols = list(instruments) if instruments else list(DEFAULT_SHADOW_INSTRUMENTS)
    ran: List[str] = []
    skipped: Dict[str, str] = {}
    errors: Dict[str, str] = {}
    results: Dict[str, Any] = {}

    for symbol in symbols:
        try:
            window = classify_window(symbol, now, 60)
        except Exception as e:
            reason = f"classify-failed:{e}"[:200]
            logger.warning("shadow_skip_classify_failed", instrument=symbol, error=str(e)[:200])
            skipped[symbol] = reason
            results[symbol] = {"status": "classify-failed", "reason": reason}
            continue
        try:
            settleable = bool((window or {}).get("settleable", False))
            reason = str((window or {}).get("reason") or "unknown")
        except Exception:
            settleable, reason = False, "unreadable-window"
        if not settleable and _is_market_closed_reason(reason):
            logger.info("shadow_skip_market_closed", instrument=symbol, reason=reason)
            skipped[symbol] = reason
            results[symbol] = {"status": "skipped-market-closed", "reason": reason}
            continue
        try:
            pair = await run_shadow_pair(
                symbol,
                horizon=horizon,
                record=True,
                forecaster=forecaster,
                now_utc=now,
                session=session,
            )
            ran.append(symbol)
            results[symbol] = {
                "status": "recorded",
                "reason": reason,
                "same_inputs_hash": pair.get("same_inputs_hash"),
                "prediction_ids": {
                    "v1": (pair.get("v1") or {}).get("prediction_id"),
                    "v2": (pair.get("v2") or {}).get("prediction_id"),
                },
            }
        except Exception as e:
            logger.warning("shadow_pair_failed", instrument=symbol, error=str(e)[:200])
            errors[symbol] = str(e)[:200]
            results[symbol] = {"status": "error", "reason": str(e)[:200]}

    summary = {
        "started_at": now.isoformat(),
        "horizon": horizon,
        "ran": ran,
        "skipped": skipped,
        "errors": errors,
        "results": results,
    }
    logger.info(
        "shadow_hourly_complete",
        ran=len(ran),
        skipped=len(skipped),
        errors=len(errors),
    )
    return summary


def run_hourly_shadow_sync(
    instruments: Optional[List[str]] = None,
    horizon: str = "1h",
) -> Dict[str, Any]:
    """Blocking wrapper for cron (``asyncio.run``). Same summary contract."""
    import asyncio

    return asyncio.run(run_hourly_shadow(instruments=instruments, horizon=horizon))


# ---------------------------------------------------------------------------
# Wiring examples (COMMENTED ONLY — do NOT enable without review; this module
# must stay side-effect free on import and is NOT wired into app startup).
# ---------------------------------------------------------------------------
# APScheduler (async worker):
#     from apscheduler.schedulers.asyncio import AsyncIOScheduler
#     from app.research.shadow_scheduler import run_hourly_shadow
#     scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
#     scheduler.add_job(run_hourly_shadow, "cron", minute=5,
#                       kwargs={"instruments": ["NIFTY 50", "BANKNIFTY"]})
#     scheduler.start()
#
# Cron (hourly, 5 min past the hour IST):
#     5 * * * * cd /app && python -c \
#       "from app.research.shadow_scheduler import run_hourly_shadow_sync; \
#        run_hourly_shadow_sync(['NIFTY 50', 'BANKNIFTY'])"
#
# FastAPI startup (main app — intentionally NOT wired):
#     @app.on_event("startup")
#     async def _start_shadow():
#         ...  # same scheduler.start() as above; keep disabled until P3-1
#         ...  # evidence review signs off on the extra hourly write load.
