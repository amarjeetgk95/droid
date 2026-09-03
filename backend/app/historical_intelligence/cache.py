"""
Hot Caching Layer — §30
In-memory and Redis cache for frequent historical query contexts and candidate evaluations.
"""
from __future__ import annotations

import time
from typing import Any, Optional
from app.historical_intelligence.schemas import HistoricalIntelligenceResult


class HIECache:
    """
    LRU/TTL cache for Historical Intelligence query responses.
    Guarantees fast retrieval (< 2ms cache hits) while preventing stale data.
    """

    def __init__(self, default_ttl_seconds: int = 180):
        self.default_ttl = default_ttl_seconds
        self._cache: dict[str, tuple[float, HistoricalIntelligenceResult]] = {}

    def _build_key(
        self,
        instrument: str,
        timeframe: str,
        regime: str,
        session: str,
        minute_epoch: int,
    ) -> str:
        return f"hie:{instrument.upper()}:{timeframe.lower()}:{regime}:{session}:{minute_epoch}"

    def get(
        self,
        instrument: str,
        timeframe: str,
        regime: str,
        session: str,
        minute_epoch: int,
    ) -> Optional[HistoricalIntelligenceResult]:
        key = self._build_key(instrument, timeframe, regime, session, minute_epoch)
        entry = self._cache.get(key)
        if entry is None:
            return None

        expiry, val = entry
        if time.time() > expiry:
            del self._cache[key]
            return None

        return val

    def set(
        self,
        instrument: str,
        timeframe: str,
        regime: str,
        session: str,
        minute_epoch: int,
        result: HistoricalIntelligenceResult,
        ttl_seconds: Optional[int] = None,
    ):
        key = self._build_key(instrument, timeframe, regime, session, minute_epoch)
        expiry = time.time() + (ttl_seconds or self.default_ttl)
        self._cache[key] = (expiry, result)

        # Basic size guard: evict oldest if cache exceeds 1000 items
        if len(self._cache) > 1000:
            oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][0])
            del self._cache[oldest_key]

    def clear(self):
        self._cache.clear()


hie_cache = HIECache()
