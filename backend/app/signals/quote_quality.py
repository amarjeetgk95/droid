"""
Quote Quality — single source of truth for "is this quote trustworthy?".

Before this module the codebase carried four divergent copies of the same
predicate, each with a different definition of unusable:

  * `signals/pipeline/data_acquisition.py:57`  — OFFLINE|DEGRADED|STALE|CLOSED|INVALID
  * `signals/scanner.py`                       — (narrower)
  * `signals/manual_signal_service.py:67`      — OFFLINE only
  * `api/signals.py`                           — (inline)

Divergent policies mean the same quote can be "live" for signal generation and
"stale" for the manual desk. This module collapses them.

Fail-closed rule: a quote is usable for *signal generation* only when it is
genuinely LIVE from a real broker. Everything else — DEGRADED, STALE, CLOSED,
OFFLINE, INVALID, UNKNOWN, and any synthetic/mock/fallback provider — is
rejected. Signal generation prices risk off spot; a stale spot silently
mis-prices every level downstream (trigger, SL, T1, T2).
"""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger()


# ─ Quality classes (mirror DataStatus plus UNKNOWN for absent quotes) ──
LIVE = "LIVE"
DEGRADED = "DEGRADED"
STALE = "STALE"
CLOSED = "CLOSED"
OFFLINE = "OFFLINE"
INVALID = "INVALID"
DISCONNECTED = "DISCONNECTED"
ERROR = "ERROR"
DEMO = "DEMO"  # legacy DataStatus, equivalent to OFFLINE
UNKNOWN = "UNKNOWN"

#: Every quality class that is *not* safe to generate a signal from.
UNUSABLE = frozenset(
    {DEGRADED, STALE, CLOSED, OFFLINE, INVALID, DISCONNECTED, ERROR, DEMO, UNKNOWN}
)

#: Ordered worst-first for substring classification of DataStatus values.
_UNUSABLE_STATUSES = (
    OFFLINE,
    INVALID,
    DISCONNECTED,
    ERROR,
    STALE,
    DEGRADED,
    CLOSED,
    DEMO,
)

#: Providers that fabricate data. Their output is never usable, whatever the status.
SYNTHETIC_PROVIDERS = frozenset({"fallback", "synthetic", "mock", "simulated", "dummy"})


class QuoteUnavailable(RuntimeError):
    """Raised when a quote is not fit for the caller's purpose (fail-closed)."""

    def __init__(self, quality: str, detail: str):
        super().__init__(detail)
        self.quality = quality
        self.detail = detail


def classify_quote(quote: Any) -> str:
    """Classify a quote object into one of the quality classes above.

    Never raises — an unreadable quote is UNKNOWN, which is unusable.
    """
    if quote is None:
        return OFFLINE
    try:
        raw_status = str(getattr(quote, "status", "") or "").upper()
        provider = str(getattr(quote, "provider", "") or "").strip().lower()
    except Exception:
        return UNKNOWN

    if provider in SYNTHETIC_PROVIDERS:
        # A synthetic provider is unusable even if it self-reports LIVE.
        return INVALID

    # DataStatus is a str Enum; `.value` and `str()` both yield the bare name,
    # but tolerate values nested in longer strings (e.g. "DataStatus.LIVE").
    for cls in _UNUSABLE_STATUSES:
        if cls in raw_status:
            return cls
    if LIVE in raw_status:
        return LIVE

    return UNKNOWN


def is_synthetic(quote: Any) -> bool:
    """True when the quote came from a fabricating provider."""
    try:
        return str(getattr(quote, "provider", "") or "").strip().lower() in SYNTHETIC_PROVIDERS
    except Exception:
        return False


def is_fallback_quote(quote: Any) -> bool:
    """Back-compat shim for the four historical copies of this predicate.

    Now delegates to the unified policy so all callers agree.
    """
    return classify_quote(quote) != LIVE


def has_price(quote: Any) -> bool:
    """True when the quote carries a positive tradable price."""
    try:
        ltp = getattr(quote, "ltp", None)
        return ltp is not None and float(ltp) > 0
    except Exception:
        return False


def is_generation_usable(quote: Any) -> bool:
    """Strict gate for signal generation: LIVE provider with a positive price."""
    return classify_quote(quote) == LIVE and has_price(quote)


def require_generation_usable(quote: Any, underlying: str = "") -> str:
    """Raise `QuoteUnavailable` unless the quote may price a new signal.

    Returns the quality class on success so callers can stamp it on the signal.
    """
    quality = classify_quote(quote)
    if quality != LIVE:
        raise QuoteUnavailable(
            quality,
            f"Live quote for {underlying or 'underlying'} is {quality}; "
            f"refusing to generate a signal off non-live data. Retry when LIVE.",
        )
    if not has_price(quote):
        raise QuoteUnavailable(
            INVALID,
            f"Live quote for {underlying or 'underlying'} carries no positive LTP.",
        )
    return quality


def describe(quote: Any) -> dict[str, Any]:
    """Diagnostic snapshot for scan reports / API payloads."""
    return {
        "quality": classify_quote(quote),
        "provider": str(getattr(quote, "provider", "") or "UNKNOWN"),
        "ltp": getattr(quote, "ltp", None),
        "synthetic": is_synthetic(quote),
        "usable_for_generation": is_generation_usable(quote),
    }
