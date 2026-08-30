import asyncio
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Any, Awaitable, TypeVar
import structlog

logger = structlog.get_logger()
T = TypeVar("T")


class CircuitState(str, Enum):
    CLOSED = "CLOSED"      # Normal operation: traffic flows through
    OPEN = "OPEN"          # Tripped: fast-fail with fallback
    HALF_OPEN = "HALF_OPEN"# Probing: limited test traffic to check health


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    pass


class CircuitBreaker:
    """3-State Circuit Breaker for upstream broker fault tolerance.
    
    Adheres strictly to Section 22 of the platform spec.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30.0,
        half_open_success_threshold: int = 2,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.half_open_success_threshold = half_open_success_threshold

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        
        self.last_failure_time: float = 0.0
        self.last_state_change_at: datetime = datetime.now(timezone.utc)
        self.total_calls: int = 0
        self.tripped_count: int = 0
        self._lock = asyncio.Lock()

    def _update_state_if_needed(self) -> None:
        """Check if recovery timeout expired and transition from OPEN to HALF_OPEN."""
        if self.state == CircuitState.OPEN:
            now = time.monotonic()
            if now - self.last_failure_time >= self.recovery_timeout_seconds:
                self.state = CircuitState.HALF_OPEN
                self.success_count = 0
                self.last_state_change_at = datetime.now(timezone.utc)
                logger.info("circuit_breaker_half_open_probing", name=self.name)

    async def _resolve_fallback(
        self,
        fallback: Callable[..., Awaitable[T] | T] | T,
        *args: Any,
        **kwargs: Any,
    ) -> T:
        if callable(fallback):
            res = fallback(*args, **kwargs)
            if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                return await res  # type: ignore
            return res  # type: ignore
        return fallback

    async def call(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        fallback: Callable[..., Awaitable[T] | T] | T | None = None,
        **kwargs: Any,
    ) -> T:
        """Execute an async operation protected by the circuit breaker."""
        async with self._lock:
            self.total_calls += 1
            self._update_state_if_needed()

            if self.state == CircuitState.OPEN:
                logger.warning("circuit_breaker_short_circuit", name=self.name)
                if fallback is not None:
                    return await self._resolve_fallback(fallback, *args, **kwargs)
                raise CircuitBreakerOpenException(f"Circuit breaker '{self.name}' is OPEN")

        # Execute the call
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except ValueError:
            # Client / validation errors shouldn't trip breaker or trigger fallback
            raise
        except Exception as e:
            await self._on_failure(str(e))
            if fallback is not None:
                return await self._resolve_fallback(fallback, *args, **kwargs)
            raise

    async def _on_success(self) -> None:
        """Handle a successful protected call."""
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.last_state_change_at = datetime.now(timezone.utc)
                    logger.info("circuit_breaker_closed_recovered", name=self.name)
            elif self.state == CircuitState.CLOSED:
                self.failure_count = 0

    async def _on_failure(self, error_reason: str) -> None:
        """Handle a failed protected call."""
        async with self._lock:
            self.last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                # Immediate trip back to OPEN if probing fails
                self.state = CircuitState.OPEN
                self.tripped_count += 1
                self.last_state_change_at = datetime.now(timezone.utc)
                logger.warning(
                    "circuit_breaker_reopened_on_probe_failure",
                    name=self.name,
                    reason=error_reason,
                )
            elif self.state == CircuitState.CLOSED:
                self.failure_count += 1
                if self.failure_count >= self.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.tripped_count += 1
                    self.last_state_change_at = datetime.now(timezone.utc)
                    logger.error(
                        "circuit_breaker_tripped_open",
                        name=self.name,
                        failures=self.failure_count,
                        reason=error_reason,
                    )

    def trip(self, reason: str = "Manual trip") -> None:
        """Manually force circuit breaker to OPEN state."""
        self.state = CircuitState.OPEN
        self.last_failure_time = time.monotonic()
        self.last_state_change_at = datetime.now(timezone.utc)
        self.tripped_count += 1
        logger.warning("circuit_breaker_manually_tripped", name=self.name, reason=reason)

    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_state_change_at = datetime.now(timezone.utc)
        logger.info("circuit_breaker_manually_reset", name=self.name)

    def get_status(self) -> dict:
        """Return diagnostic metrics for the circuit breaker."""
        self._update_state_if_needed()
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout_seconds,
            "total_calls": self.total_calls,
            "tripped_count": self.tripped_count,
            "last_state_change_at": self.last_state_change_at.isoformat(),
        }
