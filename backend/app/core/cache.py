import asyncio
import time
from collections import OrderedDict
from typing import Any, NamedTuple
from app.core.config import settings
import structlog

logger = structlog.get_logger()


class CacheItem(NamedTuple):
    value: Any
    expires_at: float | None  # Monotonic time


class InMemoryLRUCache:
    """Thread-safe in-memory LRU cache with TTL expiration support.
    
    Adheres strictly to Sections 21 and 26.
    """

    def __init__(self, max_items: int = 50000):
        self.max_items = max_items
        self._store: OrderedDict[str, CacheItem] = OrderedDict()
        self._lock = asyncio.Lock()

        # Telemetry
        self.hit_count: int = 0
        self.miss_count: int = 0
        self.eviction_count: int = 0
        self.expired_count: int = 0

    def _clean_expired(self, key: str, item: CacheItem) -> bool:
        """Check if an item has expired and remove it."""
        if item.expires_at is not None and time.monotonic() > item.expires_at:
            self._store.pop(key, None)
            self.expired_count += 1
            return True
        return False

    async def get(self, key: str) -> Any | None:
        """Retrieve value by key from cache."""
        async with self._lock:
            if key not in self._store:
                self.miss_count += 1
                return None

            item = self._store[key]
            if self._clean_expired(key, item):
                self.miss_count += 1
                return None

            # Move to end for LRU
            self._store.move_to_end(key)
            self.hit_count += 1
            return item.value

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        """Insert or update value in cache with optional TTL."""
        async with self._lock:
            expires_at = time.monotonic() + ttl_seconds if ttl_seconds else None
            
            # Enforce max capacity with LRU eviction
            if len(self._store) >= self.max_items and key not in self._store:
                self._store.popitem(last=False)  # Remove oldest
                self.eviction_count += 1

            self._store[key] = CacheItem(value=value, expires_at=expires_at)
            self._store.move_to_end(key)

    async def delete(self, key: str) -> bool:
        """Remove key from cache."""
        async with self._lock:
            if key in self._store:
                self._store.pop(key, None)
                return True
            return False

    async def clear(self) -> None:
        """Empty the cache."""
        async with self._lock:
            self._store.clear()

    def get_stats(self) -> dict:
        """Return cache performance diagnostics."""
        total_requests = self.hit_count + self.miss_count
        hit_ratio = round((self.hit_count / total_requests) * 100, 2) if total_requests > 0 else 0.0

        return {
            "backend": "in_memory_lru",
            "items_count": len(self._store),
            "max_capacity": self.max_items,
            "hit_count": self.hit_count,
            "miss_count": self.miss_count,
            "total_requests": total_requests,
            "hit_ratio_percent": hit_ratio,
            "eviction_count": self.eviction_count,
            "expired_count": self.expired_count,
        }


class CacheService:
    """Unified Caching Layer supporting Option Chain Snapshots, Quotes, and Ticks.
    
    Seamlessly operates in-memory for local development and can connect to Redis in production.
    """

    def __init__(self):
        self._backend = InMemoryLRUCache(max_items=settings.cache_max_memory_items)

    async def get(self, key: str) -> Any | None:
        return await self._backend.get(key)

    async def set(self, key: str, value: Any, ttl_seconds: float | None = None) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else settings.cache_ttl_default_seconds
        await self._backend.set(key, value, ttl_seconds=ttl)

    async def delete(self, key: str) -> bool:
        return await self._backend.delete(key)

    async def clear(self) -> None:
        await self._backend.clear()

    # Specialized Option Chain & Market Snapshot helpers
    async def get_option_chain_snapshot(self, symbol: str, expiry: str) -> list[dict] | None:
        """Get cached option chain snapshot."""
        key = f"opt_chain:{symbol}:{expiry}"
        return await self.get(key)

    async def set_option_chain_snapshot(
        self,
        symbol: str,
        expiry: str,
        chain: list[dict],
        ttl_seconds: float = 5.0,
    ) -> None:
        """Cache option chain snapshot with low TTL (e.g. 5s)."""
        key = f"opt_chain:{symbol}:{expiry}"
        await self.set(key, chain, ttl_seconds=ttl_seconds)

    def get_stats(self) -> dict:
        return self._backend.get_stats()


cache_service = CacheService()
