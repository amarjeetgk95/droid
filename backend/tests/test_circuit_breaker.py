import pytest
import asyncio
from app.core.circuit_breaker import CircuitBreaker, CircuitState, CircuitBreakerOpenException


class TestCircuitBreaker:
    @pytest.mark.asyncio
    async def test_initial_state_closed(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=3, recovery_timeout_seconds=0.1)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_trips_to_open_on_consecutive_failures(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=3, recovery_timeout_seconds=0.1)

        async def failing_func():
            raise RuntimeError("Upstream broker timeout")

        # 1st and 2nd failure: still CLOSED
        with pytest.raises(RuntimeError):
            await cb.call(failing_func)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 1

        with pytest.raises(RuntimeError):
            await cb.call(failing_func)
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 2

        # 3rd failure: trips to OPEN
        with pytest.raises(RuntimeError):
            await cb.call(failing_func)
        assert cb.state == CircuitState.OPEN
        assert cb.tripped_count == 1

    @pytest.mark.asyncio
    async def test_fallback_routing_when_open(self):
        cb = CircuitBreaker(name="test_cb", failure_threshold=2, recovery_timeout_seconds=1.0)
        cb.trip()  # Force OPEN

        async def target_func():
            return "live_data"

        def fallback_func():
            return "cached_fallback_data"

        result = await cb.call(target_func, fallback=fallback_func)
        assert result == "cached_fallback_data"

    @pytest.mark.asyncio
    async def test_half_open_probing_and_recovery(self):
        cb = CircuitBreaker(
            name="test_cb",
            failure_threshold=2,
            recovery_timeout_seconds=0.05,  # 50ms recovery timeout
            half_open_success_threshold=2,
        )
        cb.trip()
        assert cb.state == CircuitState.OPEN

        # Wait for recovery timeout to elapse
        await asyncio.sleep(0.06)

        # Next call transitions to HALF_OPEN
        async def healthy_func():
            return "success"

        # 1st probe success (still HALF_OPEN)
        res1 = await cb.call(healthy_func)
        assert res1 == "success"
        assert cb.state == CircuitState.HALF_OPEN

        # 2nd probe success (recovers to CLOSED)
        res2 = await cb.call(healthy_func)
        assert res2 == "success"
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    @pytest.mark.asyncio
    async def test_manual_reset(self):
        cb = CircuitBreaker(name="test_cb")
        cb.trip()
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0
