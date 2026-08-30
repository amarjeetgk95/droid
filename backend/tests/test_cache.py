import pytest
import asyncio
from app.core.cache import InMemoryLRUCache, CacheService


class TestCacheService:
    @pytest.mark.asyncio
    async def test_get_and_set(self):
        cache = CacheService()
        await cache.set("test_key", {"price": 25000.0})
        val = await cache.get("test_key")
        assert val == {"price": 25000.0}

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        lru = InMemoryLRUCache(max_items=10)
        # Set with 50ms TTL
        await lru.set("expiring_key", "active_data", ttl_seconds=0.05)
        val1 = await lru.get("expiring_key")
        assert val1 == "active_data"

        # Wait 60ms
        await asyncio.sleep(0.06)
        val2 = await lru.get("expiring_key")
        assert val2 is None
        assert lru.expired_count == 1

    @pytest.mark.asyncio
    async def test_lru_eviction(self):
        lru = InMemoryLRUCache(max_items=3)
        await lru.set("k1", "v1")
        await lru.set("k2", "v2")
        await lru.set("k3", "v3")

        # Access k1 to make k2 the oldest
        await lru.get("k1")

        # Insert k4 (should evict k2)
        await lru.set("k4", "v4")

        assert await lru.get("k1") == "v1"
        assert await lru.get("k2") is None
        assert await lru.get("k3") == "v3"
        assert await lru.get("k4") == "v4"
        assert lru.eviction_count == 1

    @pytest.mark.asyncio
    async def test_option_chain_snapshot_helpers(self):
        cache = CacheService()
        mock_chain = [
            {"strike": 25000, "option_type": "CE", "ltp": 120.0},
            {"strike": 25000, "option_type": "PE", "ltp": 95.0},
        ]
        await cache.set_option_chain_snapshot("NIFTY", "2026-09-03", mock_chain, ttl_seconds=10.0)
        cached = await cache.get_option_chain_snapshot("NIFTY", "2026-09-03")
        assert cached == mock_chain

    def test_cache_telemetry(self):
        cache = CacheService()
        stats = cache.get_stats()
        assert "hit_ratio_percent" in stats
        assert "items_count" in stats
        assert "max_capacity" in stats
