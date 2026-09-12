"""P3-3 forecast caches: TTL MTF 30s / options 60s / ML 15s.

Pure TTLCache (time.monotonic, max 200 keys) + per-(instrument, horizon)
key helpers + module-level default caches. TrendForecaster uses
instance-level TTLCache clones (same TTLs) so unit tests with fresh
forecasters stay hermetic while the production singleton benefits.

Env:
    FORECAST_CACHE=on/off (default on). off disables all lookups/stores;
    behavior on miss is identical to uncached.
"""

from __future__ import annotations

import os
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Tuple

MTF_TTL_S = 30.0
OPTIONS_TTL_S = 60.0
ML_TTL_S = 15.0
MAX_KEYS = 200


def cache_enabled() -> bool:
    """FORECAST_CACHE=off/false/0/no disables all forecast caches (default on)."""
    raw = (os.getenv("FORECAST_CACHE", "on") or "on").strip().lower()
    return raw not in ("false", "0", "no", "off")


class TTLCache:
    """Minimal TTL cache keyed by any hashable. Pure except time.monotonic.

    - get returns None on miss/expiry (expired entries are evicted on read).
    - set evicts oldest-inserted when over max_keys (FIFO, bounded).
    - now_fn injectable for deterministic unit tests.
    """

    def __init__(
        self,
        ttl_seconds: float,
        max_keys: int = MAX_KEYS,
        now_fn: Optional[Callable[[], float]] = None,
    ):
        self.ttl_seconds = float(ttl_seconds)
        self.max_keys = int(max_keys) if max_keys and int(max_keys) > 0 else MAX_KEYS
        self._now: Callable[[], float] = now_fn or time.monotonic
        self._store: "OrderedDict[Any, Tuple[Any, float]]" = OrderedDict()
        self.hits = 0
        self.misses = 0

    def get(self, key: Any) -> Optional[Any]:
        try:
            entry = self._store.get(key)
        except Exception:
            self.misses += 1
            return None
        if entry is None:
            self.misses += 1
            return None
        value, expires_at = entry
        try:
            now = float(self._now())
        except Exception:
            now = 0.0
        if now >= expires_at:
            try:
                self._store.pop(key, None)
            except Exception:
                pass
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, key: Any, value: Any) -> None:
        try:
            now = float(self._now())
        except Exception:
            now = 0.0
        try:
            if key in self._store:
                self._store.pop(key, None)
            self._store[key] = (value, now + float(self.ttl_seconds))
            while len(self._store) > self.max_keys:
                self._store.popitem(last=False)
        except Exception:
            pass

    def clear(self) -> None:
        try:
            self._store.clear()
        except Exception:
            pass

    def __len__(self) -> int:
        return len(self._store)


def make_mtf_key(instrument: str, timeframes: Optional[List[str]]) -> Tuple[Any, ...]:
    try:
        tfs = tuple(sorted(timeframes)) if timeframes else ()
    except Exception:
        tfs = ()
    return ("mtf", str(instrument or "UNKNOWN"), tfs)


def make_options_key(instrument: str) -> Tuple[Any, ...]:
    return ("options", str(instrument or "UNKNOWN"))


def make_ml_key(instrument: str, horizon_minutes: Optional[int]) -> Tuple[Any, ...]:
    return ("ml", str(instrument or "UNKNOWN"), horizon_minutes)


def minute_bucket_str(dt: Any) -> str:
    """UTC minute bucket 'YYYY-MM-DDTHH:MM' for idempotency keys."""
    try:
        return dt.strftime("%Y-%m-%dT%H:%M")
    except Exception:
        return "unknown-minute"


# Module-level defaults (used by pure unit tests; TrendForecaster uses
# instance-level clones with identical TTLs for test hermeticity).
MTF_CACHE = TTLCache(MTF_TTL_S, MAX_KEYS)
OPTIONS_CACHE = TTLCache(OPTIONS_TTL_S, MAX_KEYS)
ML_CACHE = TTLCache(ML_TTL_S, MAX_KEYS)


def clear_all() -> None:
    MTF_CACHE.clear()
    OPTIONS_CACHE.clear()
    ML_CACHE.clear()


__all__ = [
    "MTF_TTL_S",
    "OPTIONS_TTL_S",
    "ML_TTL_S",
    "MAX_KEYS",
    "TTLCache",
    "cache_enabled",
    "make_mtf_key",
    "make_options_key",
    "make_ml_key",
    "minute_bucket_str",
    "MTF_CACHE",
    "OPTIONS_CACHE",
    "ML_CACHE",
    "clear_all",
]
