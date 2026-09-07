"""
Central Indian Standard Time (IST) utilities for the crypto_scalp module.

Display policy (per module decision):
  - Epoch-millis storage fields (e.g. ``created_at_utc``) are intentionally
    LEFT UNCHANGED — epoch millis are timezone-agnostic instants.
  - All *human-facing* timestamps (``created_at_str``, API ``datetime``
    defaults, Telegram messages, scanner ``last_scan_time``) are produced in
    Asia/Kolkata (UTC+05:30) and labelled ``IST``.

``ZoneInfo("Asia/Kolkata")`` needs the system tz database / ``tzdata`` wheel.
On Windows hosts without it we fall back to a fixed UTC+05:30 offset, which
is correct for IST (India observes no DST).
"""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

try:  # Prefer IANA zone when available (correct, DST-free for IST anyway)
    from zoneinfo import ZoneInfo

    IST = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover - Windows without tzdata
    IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def now_ist() -> datetime:
    """Current timezone-aware time in IST."""
    return datetime.now(IST)


def now_ms() -> int:
    """Current epoch millis. Timezone-agnostic — identical for UTC/IST."""
    return int(time.time() * 1000)


def from_ms_to_ist(ms: int | float) -> datetime:
    """Convert epoch millis to an IST-aware datetime."""
    return datetime.fromtimestamp(float(ms) / 1000.0, tz=IST)


def format_ist(dt: datetime | None = None, fmt: str = "%Y-%m-%d %H:%M:%S IST") -> str:
    """Format a datetime in IST. Naive inputs are assumed to be UTC."""
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(IST)
    else:
        dt = dt.astimezone(IST)
    return dt.strftime(fmt)


def format_ms_ist(ms: int | float | None, fmt: str = "%Y-%m-%d %H:%M:%S IST") -> str:
    """Format epoch millis as an IST string. Returns '' on bad input."""
    try:
        if ms is None:
            return ""
        return from_ms_to_ist(ms).strftime(fmt)
    except Exception:
        return ""
