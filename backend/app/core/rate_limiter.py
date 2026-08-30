import asyncio
import time
from typing import NamedTuple


class RateLimitStatus(NamedTuple):
    allowed: bool
    retry_after: float
    current_tokens: float


class TokenBucketRateLimiter:
    """Token Bucket Rate Limiter for provider API request throttling.
    
    Supports:
    - Requests per second limit
    - Requests per minute limit
    - Burst limit capacity
    - Accurate Retry-After calculation
    - Non-blocking and async waiting modes
    """

    def __init__(
        self,
        requests_per_second: float = 10.0,
        requests_per_minute: float | None = 200.0,
        burst_limit: int = 20,
    ):
        self.requests_per_second = requests_per_second
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.tokens = float(burst_limit)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        
        # Effective rate is the minimum of per-second and per-minute constraints
        effective_rate = self.requests_per_second
        if self.requests_per_minute:
            effective_rate = min(effective_rate, self.requests_per_minute / 60.0)

        # Add new tokens based on elapsed time
        self.tokens = min(float(self.burst_limit), self.tokens + elapsed * effective_rate)
        self.last_refill = now

    def check(self, tokens_required: float = 1.0) -> RateLimitStatus:
        """Non-blocking check if a request is allowed."""
        self._refill()
        if self.tokens >= tokens_required:
            return RateLimitStatus(allowed=True, retry_after=0.0, current_tokens=self.tokens)

        effective_rate = self.requests_per_second
        if self.requests_per_minute:
            effective_rate = min(effective_rate, self.requests_per_minute / 60.0)

        missing = tokens_required - self.tokens
        retry_after = missing / effective_rate if effective_rate > 0 else 1.0
        return RateLimitStatus(allowed=False, retry_after=retry_after, current_tokens=self.tokens)

    async def acquire(self, tokens_required: float = 1.0) -> None:
        """Asynchronously acquire tokens, waiting if rate limit is exceeded."""
        while True:
            async with self._lock:
                status = self.check(tokens_required)
                if status.allowed:
                    self.tokens -= tokens_required
                    return
                wait_time = status.retry_after
            
            # Wait outside the lock
            await asyncio.sleep(wait_time)

    def try_acquire(self, tokens_required: float = 1.0) -> bool:
        """Synchronous attempt to acquire token without waiting."""
        self._refill()
        if self.tokens >= tokens_required:
            self.tokens -= tokens_required
            return True
        return False
