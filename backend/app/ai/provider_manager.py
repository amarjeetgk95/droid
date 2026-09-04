"""
Provider Manager — §2, §9, §10, §21

Manages AI provider lifecycle, health checks, and failover.
Singleton per process.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Optional, Literal
import structlog

from app.ai.schemas import (
    ProviderMetrics,
    AIProviderStatus,
    ProviderConfig,
)

logger = structlog.get_logger()


class ProviderState:
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.status = AIProviderStatus.ACTIVE
        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.last_ping_time: Optional[datetime] = None
        self.last_failure_time: Optional[datetime] = None
        self.last_success_time: Optional[datetime] = None
        self.total_requests = 0
        self.total_failures = 0
        self.total_timeouts = 0
        self.total_errors = 0

    def record_success(self) -> None:
        self.consecutive_successes += 1
        self.consecutive_failures = 0
        self.last_success_time = datetime.now(timezone.utc)
        self.total_requests += 1
        if self.consecutive_successes >= 3:
            if self.status == AIProviderStatus.DEGRADED:
                self.status = AIProviderStatus.ACTIVE
                logger.info("provider_recovered", provider=self.config.provider)

    def record_failure(self, is_timeout: bool = False) -> None:
        self.consecutive_failures += 1
        self.consecutive_successes = 0
        self.last_failure_time = datetime.now(timezone.utc)
        self.total_requests += 1
        if is_timeout:
            self.total_timeouts += 1
        else:
            self.total_errors += 1
            self.total_failures += 1

        degrades = self.config.consecutive_failures_to_degrade
        suspends = self.config.consecutive_failures_to_suspend

        if self.consecutive_failures >= suspends:
            self.status = AIProviderStatus.SUSPENDED
            logger.warning("provider_suspended", provider=self.config.provider, failures=self.consecutive_failures)
        elif self.consecutive_failures >= degrades:
            self.status = AIProviderStatus.DEGRADED
            logger.warning("provider_degraded", provider=self.config.provider, failures=self.consecutive_failures)

    def reset(self) -> None:
        self.status = AIProviderStatus.ACTIVE
        self.consecutive_failures = 0
        self.consecutive_successes = 0

    def can_handle_request(self) -> bool:
        return self.status != AIProviderStatus.SUSPENDED


class ProviderManager:
    """
    Manages AI provider lifecycle, health checks, and failover.

    Per §10:
    - Health checks every 15s
    - Two consecutive failed pings -> SUSPENDED
    - Three consecutive successful pings -> ACTIVE
    - Failover order from config
    """

    def __init__(self):
        self._providers: dict[str, ProviderState] = {}
        self._health_check_tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._health_check_interval = 15.0

    def register_provider(self, config: ProviderConfig) -> None:
        """Register a provider with its configuration."""
        state = ProviderState(config)
        self._providers[config.provider] = state
        logger.info("provider_registered", provider=config.provider, model=config.model, is_primary=config.is_primary)

    def unregister_provider(self, provider: str) -> None:
        """Unregister a provider."""
        if provider in self._providers:
            del self._providers[provider]
            task = self._health_check_tasks.pop(provider, None)
            if task:
                task.cancel()
            logger.info("provider_unregistered", provider=provider)

    def get_provider(self, path: Literal["scalping", "core"], failover_order: list[str]) -> Optional[str]:
        """
        Get next available provider following failover order.

        Args:
            path: "scalping" or "core"
            failover_order: List of provider names in priority order

        Returns:
            Provider name or None if no provider available
        """
        for provider in failover_order:
            state = self._providers.get(provider)
            if state and state.can_handle_request():
                return provider
        if not self._providers and failover_order:
            return failover_order[0]
        return None

    def record_success(self, provider: str) -> None:
        """Record successful request."""
        state = self._providers.get(provider)
        if state:
            state.record_success()

    def record_failure(self, provider: str, is_timeout: bool = False) -> None:
        """Record failed request."""
        state = self._providers.get(provider)
        if state:
            state.record_failure(is_timeout=is_timeout)

    def get_metrics(self, provider: str) -> Optional[ProviderMetrics]:
        """Get provider metrics."""
        state = self._providers.get(provider)
        if not state:
            return None
        return ProviderMetrics(
            provider=state.config.provider,
            model=state.config.model,
            request_id="",
            latency_ms=0,
            status=state.status.value,
            timestamp=datetime.now(timezone.utc),
        )

    def get_status(self, provider: str) -> Optional[AIProviderStatus]:
        """Get current provider status."""
        state = self._providers.get(provider)
        return state.status if state else None

    def is_healthy(self, provider: str) -> bool:
        """Check if provider is healthy enough for traffic."""
        state = self._providers.get(provider)
        return state.can_handle_request() if state else False

    def get_failover_order(self, path: Literal["scalping", "core"], config: dict) -> list[str]:
        """Get failover order from config or use default."""
        key = f"{path}_failover_order"
        default = ["openrouter", "gemini"]
        return config.get(key, default)

    async def health_check_provider(self, provider: str, health_fn) -> bool:
        """
        Perform health check on a provider.

        Args:
            provider: Provider name
            health_fn: Async function to call for health check

        Returns:
            True if health check passed
        """
        state = self._providers.get(provider)
        if not state:
            return False

        try:
            result = await asyncio.wait_for(health_fn(), timeout=5.0)
            state.record_success()
            return True
        except asyncio.TimeoutError:
            state.record_failure(is_timeout=True)
            return False
        except Exception as e:
            state.record_failure()
            logger.debug("health_check_failed", provider=provider, error=str(e))
            return False

    async def start_health_checks(self, health_check_fn) -> None:
        """Start background health checks for all providers."""
        self._running = True
        while self._running:
            for provider, state in list(self._providers.items()):
                if not state.config.is_primary:
                    continue
                asyncio.create_task(self.health_check_provider(provider, health_check_fn))
            await asyncio.sleep(self._health_check_interval)

    def stop_health_checks(self) -> None:
        """Stop background health checks."""
        self._running = False
        for task in self._health_check_tasks.values():
            task.cancel()
        self._health_check_tasks.clear()

    def get_all_metrics(self) -> dict:
        """Get metrics for all providers."""
        return {
            provider: {
                "status": state.status.value,
                "total_requests": state.total_requests,
                "total_failures": state.total_failures,
                "total_timeouts": state.total_timeouts,
                "failure_rate": state.total_failures / state.total_requests if state.total_requests > 0 else 0,
                "consecutive_failures": state.consecutive_failures,
                "consecutive_successes": state.consecutive_successes,
            }
            for provider, state in self._providers.items()
        }


provider_manager = ProviderManager()
