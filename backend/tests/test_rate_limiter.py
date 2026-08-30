import pytest
import asyncio
from app.core.rate_limiter import TokenBucketRateLimiter


class TestTokenBucketRateLimiter:
    def test_burst_capacity(self):
        limiter = TokenBucketRateLimiter(requests_per_second=10.0, burst_limit=5)
        # Should allow 5 requests immediately
        for _ in range(5):
            assert limiter.try_acquire() is True
        # 6th request exceeds burst limit
        assert limiter.try_acquire() is False

    def test_retry_after_estimation(self):
        limiter = TokenBucketRateLimiter(requests_per_second=10.0, requests_per_minute=None, burst_limit=1)
        limiter.try_acquire()  # Consume the 1 token
        status = limiter.check(1.0)
        assert status.allowed is False
        assert 0.0 < status.retry_after <= 0.15

    @pytest.mark.asyncio
    async def test_async_acquire_refills(self):
        limiter = TokenBucketRateLimiter(requests_per_second=50.0, burst_limit=1)
        await limiter.acquire(1.0)
        # Immediate next acquire will wait ~20ms and succeed
        await limiter.acquire(1.0)
        assert limiter.tokens >= 0.0
