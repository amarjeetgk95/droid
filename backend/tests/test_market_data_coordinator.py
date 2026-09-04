import asyncio
import pytest
from app.services.market_data_coordinator import MarketDataCoordinator
from app.services.central_feed import CentralMarketDataFeed, central_feed

@pytest.mark.asyncio
async def test_coordinator_single_flight_coalescing():
    coordinator = MarketDataCoordinator()
    call_count = 0

    async def expensive_producer():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.05)
        return {"data": 42}

    # Launch 10 concurrent requests for the same key
    results = await asyncio.gather(*[
        coordinator.get_or_compute("test_key", expensive_producer, ttl_seconds=5.0)
        for _ in range(10)
    ])

    assert call_count == 1
    assert len(results) == 10
    for res in results:
        assert res.data == {"data": 42}
        assert res.status == "FRESH"

@pytest.mark.asyncio
async def test_coordinator_ttl_expiration():
    coordinator = MarketDataCoordinator()
    call_count = 0

    async def producer():
        nonlocal call_count
        call_count += 1
        return {"count": call_count}

    res1 = await coordinator.get_or_compute("expiring_key", producer, ttl_seconds=0.05)
    assert res1.data == {"count": 1}

    # Calling immediately should hit cache
    res2 = await coordinator.get_or_compute("expiring_key", producer, ttl_seconds=0.05)
    assert res2.data == {"count": 1}
    assert call_count == 1

    # Wait for TTL to expire
    await asyncio.sleep(0.06)
    res3 = await coordinator.get_or_compute("expiring_key", producer, ttl_seconds=0.05)
    assert res3.data == {"count": 2}
    assert call_count == 2

@pytest.mark.asyncio
async def test_coordinator_degraded_fallback_on_error():
    coordinator = MarketDataCoordinator()
    should_fail = False

    async def flaky_producer():
        if should_fail:
            raise RuntimeError("Broker connection timeout")
        return {"price": 100.0}

    # Initial successful call
    res1 = await coordinator.get_or_compute("flaky_key", flaky_producer, ttl_seconds=0.02, fallback_stale=True)
    assert res1.data == {"price": 100.0}
    assert res1.status == "FRESH"

    await asyncio.sleep(0.03)
    should_fail = True

    # Producer fails, but coordinator returns stale cache as degraded fallback
    res2 = await coordinator.get_or_compute("flaky_key", flaky_producer, ttl_seconds=0.02, fallback_stale=True)
    assert res2.data == {"price": 100.0}
    assert res2.status == "DEGRADED"

@pytest.mark.asyncio
async def test_central_feed_registration_and_backpressure():
    feed = CentralMarketDataFeed()
    mock_ws = object()
    queue = await feed.register_client(mock_ws)
    assert queue.maxsize == CentralMarketDataFeed.CLIENT_QUEUE_MAXSIZE
    assert mock_ws in feed._subscribers

    await feed.unregister_client(mock_ws)
    assert mock_ws not in feed._subscribers

