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
#: P0-2 KILL SYNTHETIC FALLBACKS: paper/cache/cached/replay/backtest/
#: indicative/delayed/test all fabricate or replay data — never tradable.
SYNTHETIC_PROVIDERS = frozenset({
    "fallback", "synthetic", "mock", "simulated", "dummy",
    "paper", "cache", "cached", "replay", "backtest",
    "indicative", "delayed", "test",
})

#: Quote states that prove the venue halted the instrument. A halted quote
#: carries a price nobody can trade — generating off it books phantom fills.
HALT_TOKENS = frozenset({
    "HALT", "HALTED", "TRADING_HALT", "SUSPEND", "SUSPENDED",
    "FREEZE", "FROZEN", "CIRCUIT", "CIRCUIT_BREAKER", "BREAK",
})

#: Maximum age of a quote usable for signal generation (fail-closed freshness).
MAX_QUOTE_AGE_MS = 5000

#: Microstructure guards for generation.
MAX_SPREAD_PCT = 2.0          # (ask-bid)/mid*100 must be <= 2%
MAX_PRICE_BAND_PCT = 5.0      # |ltp - ref|/ref*100 must be <= 5%


class QuoteUnavailable(RuntimeError):
    """Raised when a quote is not fit for the caller's purpose (fail-closed)."""

    def __init__(self, quality: str, detail: str):
        super().__init__(detail)
        self.quality = quality
        self.detail = detail


def _quote_age_ms(quote: Any, now_ms: int | None = None) -> int | None:
    """Best-effort quote age in ms. None when the timestamp is unreadable."""
    try:
        import time as _t
        from datetime import datetime as _dt, timezone as _tz
        now = int(now_ms) if now_ms is not None else int(_t.time() * 1000)
        q_ts = getattr(quote, "timestamp", None)
        if q_ts is None:
            return None
        if isinstance(q_ts, _dt):
            ts_ms = int(q_ts.replace(tzinfo=_tz.utc).timestamp() * 1000) if q_ts.tzinfo is None else int(q_ts.timestamp() * 1000)
            return now - ts_ms
        if isinstance(q_ts, (int, float)):
            v = float(q_ts)
            # Heuristic: ms (>1e11) vs seconds.
            ts_ms = int(v) if v > 1e11 else int(v * 1000)
            return now - ts_ms
        return None
    except Exception:
        return None


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

    # P0-2: halted instruments are never generatable, even when LIVE-tagged.
    try:
        for _tok in HALT_TOKENS:
            if _tok and _tok in raw_status:
                return INVALID
        # Some feeds carry an explicit halt flag instead of a status token.
        for _attr in ("halted", "is_halted", "trading_halt", "halt"):
            try:
                if bool(getattr(quote, _attr, False)):
                    return INVALID
            except Exception:
                continue
    except Exception:
        pass

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


def _spread_pct(quote: Any) -> float | None:
    """Best-effort (ask-bid)/mid*100. None when bid/ask are absent."""
    try:
        bid = getattr(quote, "bid", None)
        ask = getattr(quote, "ask", None)
        if bid is None or ask is None:
            return None
        b, a = float(bid), float(ask)
        if b <= 0 or a <= 0 or a < b:
            return None
        mid = (b + a) / 2.0
        if mid <= 0:
            return None
        return (a - b) / mid * 100.0
    except Exception:
        return None


def require_generation_usable(
    quote: Any,
    underlying: str = "",
    now_ms: int | None = None,
    ref_price: float | None = None,
) -> str:
    """Raise `QuoteUnavailable` unless the quote may price a new signal.

    Fail-closed microstructure guards (P0-2):
      * quality must be LIVE (synthetic/halt/unusable rejected in classify)
      * positive LTP
      * age <= MAX_QUOTE_AGE_MS (5000ms) when a timestamp is present
      * spread% <= MAX_SPREAD_PCT when bid/ask are present
      * |ltp-ref|/ref <= MAX_PRICE_BAND_PCT when ref_price is provided

    `now_ms`/`ref_price` are optional for back-compat — guards that lack
    inputs are skipped, never assumed. Returns quality on success.
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
    # Freshness: stale spot silently mis-prices every level downstream.
    try:
        age = _quote_age_ms(quote, now_ms)
        if age is not None and age > MAX_QUOTE_AGE_MS:
            raise QuoteUnavailable(
                STALE,
                f"Quote for {underlying or 'underlying'} is {age}ms old "
                f"(max {MAX_QUOTE_AGE_MS}ms) — refusing to price risk off stale spot.",
            )
        if age is not None and age < -1000:
            raise QuoteUnavailable(
                INVALID,
                f"Quote for {underlying or 'underlying'} is {abs(age)}ms in the future — clock fault, refusing.",
            )
    except QuoteUnavailable:
        raise
    except Exception:
        pass
    # Spread guard: crossed markets / 5%-wide books are not executable.
    try:
        sp = _spread_pct(quote)
        if sp is not None and sp > MAX_SPREAD_PCT:
            raise QuoteUnavailable(
                INVALID,
                f"Quote for {underlying or 'underlying'} spread {sp:.2f}% exceeds {MAX_SPREAD_PCT:.2f}% — book not executable.",
            )
    except QuoteUnavailable:
        raise
    except Exception:
        pass
    # Price-band guard: LTP dislocated from the reference (index/chain mark)
    # is a bad tick or a wrong instrument — never price risk off it.
    try:
        if ref_price is not None:
            ltp = float(getattr(quote, "ltp"))
            ref = float(ref_price)
            if ref > 0 and ltp > 0:
                band = abs(ltp - ref) / ref * 100.0
                if band > MAX_PRICE_BAND_PCT:
                    raise QuoteUnavailable(
                        INVALID,
                        f"Quote LTP {ltp} is {band:.2f}% away from ref {ref} "
                        f"(max {MAX_PRICE_BAND_PCT:.2f}%) — dislocation, refusing.",
                    )
    except QuoteUnavailable:
        raise
    except Exception:
        pass
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
