"""
Market Data Coordinator — Centralized Ingestion & Single-Flight Coalescing Engine

Core Architecture Contract:
1. One shared market-data production pipeline.
2. Single-flight request coalescing: N concurrent callers share 1 upstream evaluation.
3. Multi-tier TTL cache (Tier A live, Tier B fast derived, Tier C analytical, Tier D slow institutional).
4. Market session awareness: relaxes polling outside trading hours.
5. Standardized CachedValue model with freshness tracking and degraded fallback.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine, Literal

import structlog

from app.services.calendar_service import calendar_service

logger = structlog.get_logger(__name__)


@dataclass
class CachedValue:
    data: Any
    updated_at: datetime
    source: str
    status: Literal["FRESH", "STALE", "DEGRADED", "UNAVAILABLE"]
    age_ms: int = 0
    derived_from: dict[str, str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "data": self.data,
            "updated_at": self.updated_at.isoformat(),
            "source": self.source,
            "status": self.status,
            "age_ms": self.age_ms,
            "derived_from": self.derived_from,
        }


class CacheProvider:
    """Storage abstraction for coordinator cache (Phase 5 multi-worker readiness).

    Default is in-process memory. Swap in RedisCacheProvider for
    multi-worker uvicorn deployments (shared cache + pub/sub).
    """

    async def get(self, key: str) -> tuple[float, CachedValue] | None:
        raise NotImplementedError

    async def set(self, key: str, value: tuple[float, CachedValue]) -> None:
        raise NotImplementedError

    async def delete(self, key: str) -> None:
        raise NotImplementedError

    async def clear(self) -> None:
        raise NotImplementedError

    async def keys(self) -> list[str]:
        raise NotImplementedError


class InMemoryCacheProvider(CacheProvider):
    """Default single-process cache provider (active)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, CachedValue]] = {}

    async def get(self, key: str) -> tuple[float, CachedValue] | None:
        return self._store.get(key)

    async def set(self, key: str, value: tuple[float, CachedValue]) -> None:
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def clear(self) -> None:
        self._store.clear()

    async def keys(self) -> list[str]:
        return list(self._store.keys())


class RedisCacheProvider(CacheProvider):
    """Distributed cache provider for multi-worker deployments (standby).

    Uses Redis for shared storage + pub/sub invalidation. Lazily imports
    redis so single-process deployments don't require the dependency.
    Falls back gracefully when Redis is unreachable (caller serves
    degraded/stale via coordinator fallback path).
    """

    def __init__(self, url: str = "redis://localhost:6379/0", prefix: str = "mdc:"):
        self._url = url
        self._prefix = prefix
        self._client: Any | None = None
        # Local in-memory overlay so cache hits stay <15ms even if Redis is slow.
        self._overlay = InMemoryCacheProvider()

    async def _client_or_none(self) -> Any | None:
        if self._client is not None:
            return self._client
        try:
            import redis.asyncio as redis  # type: ignore

            self._client = redis.from_url(self._url, decode_responses=False)
            return self._client
        except Exception:
            logger.warning("redis_cache_provider_unavailable", url=self._url)
            return None

    def _rkey(self, key: str) -> str:
        return f"{self._prefix}{key}"

    async def get(self, key: str) -> tuple[float, CachedValue] | None:
        # Fast path: local overlay first.
        hit = await self._overlay.get(key)
        if hit is not None:
            return hit
        client = await self._client_or_none()
        if client is None:
            return None
        try:
            import pickle

            raw = await client.get(self._rkey(key))
            if raw is None:
                return None
            entry = pickle.loads(raw)
            await self._overlay.set(key, entry)
            return entry
        except Exception:
            logger.debug("redis_cache_get_failed", key=key)
            return None

    async def set(self, key: str, value: tuple[float, CachedValue]) -> None:
        await self._overlay.set(key, value)
        client = await self._client_or_none()
        if client is None:
            return
        try:
            import pickle

            # Best-effort mirror; TTL enforced by coordinator, Redis expiry is a guard.
            await client.set(self._rkey(key), pickle.dumps(value), ex=3600)
        except Exception:
            logger.debug("redis_cache_set_failed", key=key)

    async def delete(self, key: str) -> None:
        await self._overlay.delete(key)
        client = await self._client_or_none()
        if client is None:
            return
        try:
            await client.delete(self._rkey(key))
        except Exception:
            pass

    async def clear(self) -> None:
        await self._overlay.clear()
        client = await self._client_or_none()
        if client is None:
            return
        try:
            async for k in client.scan_iter(f"{self._prefix}*"):
                await client.delete(k)
        except Exception:
            pass

    async def keys(self) -> list[str]:
        return await self._overlay.keys()


class MarketDataCoordinator:
    """Centralized market-data coordinator for all backend consumers."""

    # Tiered TTLs (seconds) — see architecture plan data classification:
    #   Tier A (live push):      cards=2.0, quotes/quote=1.5
    #   Tier B (fast derived):   breadth=5.0, health=5.0, status=5.0
    #   Tier C (analytical):     regime=45.0, ml=45.0
    #   Tier D (institutional):  fii_dii=900.0 (15 min)
    DEFAULT_TTLS: dict[str, float] = {
        "cards": 2.0,
        "quotes": 1.5,
        "quote": 1.5,
        "breadth": 5.0,
        "health": 5.0,
        "status": 5.0,
        "regime": 45.0,
        "ml": 45.0,
        "fii_dii": 900.0,  # 15 minutes
    }

    # Extended TTL multiplier when market is closed, weekend, or holiday
    CLOSED_SESSION_TTL_MULTIPLIER = 4.0

    def __init__(self, cache_provider: CacheProvider | None = None):
        if cache_provider is None:
            try:
                from app.core.config import settings
                if getattr(settings, "redis_url", None):
                    cache_provider = RedisCacheProvider(url=settings.redis_url)
            except Exception:
                pass
        self._cache_provider: CacheProvider = cache_provider or InMemoryCacheProvider()
        # Back-compat alias: some call sites/tests touch _cache directly.
        # Keep it pointing at the in-memory store when applicable.
        overlay = self._cache_provider
        if isinstance(overlay, InMemoryCacheProvider):
            self._cache: dict[str, tuple[float, CachedValue]] = overlay._store
        else:
            self._cache = {}  # type: ignore[assignment]
        self._locks: dict[str, asyncio.Lock] = {}
        self._in_flight: dict[str, asyncio.Future] = {}
        self._master_lock = asyncio.Lock()

        # Telemetry
        self.stats: dict[str, int] = {
            "hits": 0,
            "misses": 0,
            "coalesced_requests": 0,
            "refreshes": 0,
            "failures": 0,
        }

    def _get_ttl(self, key: str) -> float:
        base_key = key.split(":")[0]
        base_ttl = self.DEFAULT_TTLS.get(base_key, 5.0)
        # Check session: if closed/weekend, extend TTL
        try:
            now = datetime.now(timezone.utc)
            if not calendar_service.is_trading_day(now.date()) or not calendar_service.is_market_open_now():
                return base_ttl * self.CLOSED_SESSION_TTL_MULTIPLIER
        except Exception:
            pass
        return base_ttl

    async def _get_key_lock(self, key: str) -> asyncio.Lock:
        async with self._master_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    async def _cache_get(self, key: str) -> tuple[float, CachedValue] | None:
        """Read through CacheProvider, keeping the _cache alias in sync for stats."""
        try:
            entry = await self._cache_provider.get(key)
        except Exception:
            entry = None
        if entry is not None and isinstance(self._cache_provider, InMemoryCacheProvider):
            # Alias already shares the same dict; no extra work.
            pass
        elif entry is not None:
            # Mirror distributed hits locally for get_stats() visibility.
            try:
                self._cache[key] = entry
            except Exception:
                pass
        else:
            # Provider miss — fall back to local mirror (covers Redis overlay lag).
            try:
                entry = self._cache.get(key)
            except Exception:
                entry = None
        return entry

    async def _cache_set(self, key: str, value: tuple[float, CachedValue]) -> None:
        try:
            await self._cache_provider.set(key, value)
        except Exception:
            logger.debug("coordinator_cache_set_failed", key=key)
        try:
            self._cache[key] = value
        except Exception:
            pass

    async def invalidate(self, key: str) -> None:
        """Explicit invalidation (e.g. on-change refresh for Tier D)."""
        try:
            await self._cache_provider.delete(key)
        except Exception:
            pass
        try:
            self._cache.pop(key, None)
        except Exception:
            pass

    async def clear(self) -> None:
        try:
            await self._cache_provider.clear()
        except Exception:
            pass
        try:
            self._cache.clear()
        except Exception:
            pass

    async def get_or_compute(
        self,
        key: str,
        fetcher: Callable[[], Coroutine[Any, Any, Any]],
        source_name: str = "coordinator",
        force_refresh: bool = False,
        ttl_seconds: float | None = None,
        fallback_stale: bool = True,
        max_retries: int = 1,
        backoff_initial: float = 0.1,
        derived_from: dict[str, str] | None = None,
    ) -> CachedValue:
        """Get cached value, or compute using single-flight request coalescing."""
        now_mono = time.monotonic()
        ttl = ttl_seconds if ttl_seconds is not None else self._get_ttl(key)

        # 1. Fast path: check cache under no lock
        cached_entry = await self._cache_get(key)
        if not force_refresh and cached_entry is not None:
            cached_mono, cached_val = cached_entry
            age_sec = now_mono - cached_mono
            if age_sec < ttl:
                self.stats["hits"] += 1
                return CachedValue(
                    data=cached_val.data,
                    updated_at=cached_val.updated_at,
                    source=cached_val.source,
                    status="FRESH",
                    age_ms=int(age_sec * 1000),
                    derived_from=cached_val.derived_from,
                )

        # 2. Check if an existing refresh is already in-flight (Single-Flight coalescing)
        in_flight_future: asyncio.Future | None = None
        async with self._master_lock:
            if key in self._in_flight:
                in_flight_future = self._in_flight[key]
                self.stats["coalesced_requests"] += 1

        if in_flight_future is not None:
            # Wait for the in-flight operation initiated by another coroutine
            try:
                result = await in_flight_future
                return result
            except Exception:
                # If in-flight failed, proceed to acquire lock and retry
                pass

        # 3. Acquire per-key lock to initiate compute
        lock = await self._get_key_lock(key)
        async with lock:
            # Re-check cache after acquiring lock
            now_mono = time.monotonic()
            cached_entry = await self._cache_get(key)
            if not force_refresh and cached_entry is not None:
                cached_mono, cached_val = cached_entry
                age_sec = now_mono - cached_mono
                if age_sec < ttl:
                    self.stats["hits"] += 1
                    cached_val.age_ms = int(age_sec * 1000)
                    cached_val.status = "FRESH"
                    return cached_val

            # Register in-flight future for other concurrent callers
            loop = asyncio.get_running_loop()
            current_future = loop.create_future()
            async with self._master_lock:
                self._in_flight[key] = current_future

            self.stats["misses"] += 1
            self.stats["refreshes"] += 1

            try:
                attempt = 0
                raw_data = None
                last_exc: Exception | None = None

                while attempt <= max_retries:
                    try:
                        # Execute upstream fetcher with a bounded timeout (8.0s)
                        raw_data = await asyncio.wait_for(fetcher(), timeout=8.0)
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        attempt += 1
                        if attempt <= max_retries:
                            await asyncio.sleep(backoff_initial * (2 ** (attempt - 1)))

                if last_exc is None:
                    new_val = CachedValue(
                        data=raw_data,
                        updated_at=datetime.now(timezone.utc),
                        source=source_name,
                        status="FRESH",
                        age_ms=0,
                        derived_from=derived_from,
                    )
                    await self._cache_set(key, (time.monotonic(), new_val))
                    if not current_future.done():
                        current_future.set_result(new_val)
                    return new_val

                # All retry attempts failed
                self.stats["failures"] += 1
                logger.warning(
                    "coordinator_fetch_failed",
                    key=key,
                    source=source_name,
                    error=str(last_exc)[:200],
                    attempts=attempt,
                )

                # Graceful degraded fallback: if we have any prior cached value, return it as STALE/DEGRADED
                if cached_entry is not None:
                    _, last_val = cached_entry
                    degraded_val = CachedValue(
                        data=last_val.data,
                        updated_at=last_val.updated_at,
                        source=last_val.source,
                        status="DEGRADED",
                        age_ms=int((time.monotonic() - cached_entry[0]) * 1000),
                        derived_from=last_val.derived_from,
                    )
                    if not current_future.done():
                        current_future.set_result(degraded_val)
                    return degraded_val

                # If no prior cache, return UNAVAILABLE
                unavailable_val = CachedValue(
                    data=None,
                    updated_at=datetime.now(timezone.utc),
                    source=source_name,
                    status="UNAVAILABLE",
                    age_ms=0,
                    derived_from=derived_from,
                )
                if not current_future.done():
                    current_future.set_result(unavailable_val)
                return unavailable_val

            finally:
                async with self._master_lock:
                    self._in_flight.pop(key, None)

    async def get_many(
        self,
        fetch_specs: dict[str, tuple[Callable[[], Coroutine[Any, Any, Any]], str]],
        force_refresh: bool = False,
    ) -> dict[str, CachedValue]:
        """Fetch multiple cached components concurrently using single-flight."""
        tasks = [
            self.get_or_compute(key, fetcher, source_name=src, force_refresh=force_refresh)
            for key, (fetcher, src) in fetch_specs.items()
        ]
        results = await asyncio.gather(*tasks, return_exceptions=False)
        return dict(zip(fetch_specs.keys(), results))

    def get_stats(self) -> dict[str, Any]:
        return {
            **self.stats,
            "cached_keys": list(self._cache.keys()),
            "cached_count": len(self._cache),
            "in_flight_count": len(self._in_flight),
        }


market_data_coordinator = MarketDataCoordinator()
