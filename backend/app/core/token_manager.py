import random
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Awaitable
from pydantic import BaseModel, Field
import structlog

logger = structlog.get_logger()


class ConnectionState(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    AUTHENTICATING = "AUTHENTICATING"
    CONNECTED = "CONNECTED"
    DEGRADED = "DEGRADED"
    RECONNECTING = "RECONNECTING"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    RATE_LIMITED = "RATE_LIMITED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    MANUAL_STOP = "MANUAL_STOP"


class TokenInfo(BaseModel):
    access_token: str = ""
    refresh_token: str | None = None
    token_type: str = "Bearer"
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    provider: str = "mock"


class TokenManager:
    """Manages broker authentication tokens and WebSocket connection state lifecycle.
    
    Adheres to Master Prompt Sections 8, 9, 10, and 11.
    """

    def __init__(
        self,
        provider: str = "mock",
        initial_backoff: float = 1.0,
        max_backoff: float = 60.0,
        enable_jitter: bool = True,
    ):
        self.provider = provider
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.enable_jitter = enable_jitter

        self.state: ConnectionState = ConnectionState.DISCONNECTED
        self.token_info: TokenInfo | None = None
        
        # Telemetry & Heartbeat Tracking
        self.connection_started_at: datetime | None = None
        self.last_message_at: datetime | None = None
        self.last_heartbeat_at: datetime | None = None
        self.reconnect_count: int = 0
        self.subscription_count: int = 0
        self.last_error: str | None = None

        # Callbacks for refresh
        self._refresh_callback: Callable[[], Awaitable[TokenInfo]] | None = None

    def register_refresh_callback(self, callback: Callable[[], Awaitable[TokenInfo]]) -> None:
        """Register a callback that fetches a new/refreshed access token."""
        self._refresh_callback = callback

    def set_token(self, token_info: TokenInfo) -> None:
        """Set the active token info."""
        self.token_info = token_info
        if self.state == ConnectionState.AUTH_EXPIRED:
            self.set_state(ConnectionState.DISCONNECTED)

    def set_state(self, state: ConnectionState, reason: str | None = None) -> None:
        """Transition connection lifecycle state."""
        old_state = self.state
        self.state = state
        if reason:
            self.last_error = reason
        
        if state == ConnectionState.CONNECTED and old_state != ConnectionState.CONNECTED:
            self.connection_started_at = datetime.now(timezone.utc)
            self.reconnect_count = 0  # Reset backoff after stable connection
        
        logger.info(
            "connection_state_changed",
            provider=self.provider,
            old_state=old_state.value,
            new_state=state.value,
            reason=reason,
        )

    def is_token_expired(self) -> bool:
        """Check if current token is expired or close to expiry (within 60s)."""
        if not self.token_info or not self.token_info.access_token:
            return True
        if self.token_info.expires_at is None:
            return False
        
        now = datetime.now(timezone.utc)
        return now >= self.token_info.expires_at

    async def get_valid_token(self) -> str:
        """Get a valid access token, triggering refresh if supported and expired."""
        if self.provider == "mock":
            return "mock-demo-token"

        if self.is_token_expired():
            if self._refresh_callback:
                try:
                    logger.info("refreshing_expired_token", provider=self.provider)
                    new_token = await self._refresh_callback()
                    self.set_token(new_token)
                    return new_token.access_token
                except Exception as e:
                    self.mark_expired(str(e))
                    raise RuntimeError(f"Token refresh failed for {self.provider}: {e}")
            else:
                self.mark_expired("Token expired and no refresh callback registered")
                raise RuntimeError(f"Re-authentication required for {self.provider}")

        return self.token_info.access_token if self.token_info else ""

    def mark_expired(self, reason: str = "Access token expired") -> None:
        """Mark token as expired and notify system."""
        self.set_state(ConnectionState.AUTH_EXPIRED, reason=reason)

    def record_heartbeat(self) -> None:
        """Record received provider heartbeat."""
        self.last_heartbeat_at = datetime.now(timezone.utc)

    def record_message(self) -> None:
        """Record received market message/tick."""
        self.last_message_at = datetime.now(timezone.utc)

    def record_reconnect_attempt(self) -> float:
        """Record a reconnection attempt and calculate backoff delay with jitter."""
        self.reconnect_count += 1
        self.set_state(ConnectionState.RECONNECTING)
        
        # Exponential backoff: min(max_backoff, initial_backoff * 2^(count-1))
        delay = min(self.max_backoff, self.initial_backoff * (2 ** (self.reconnect_count - 1)))
        
        # Add jitter if enabled (+- 20% random variation)
        if self.enable_jitter:
            jitter_range = delay * 0.2
            delay = delay + random.uniform(-jitter_range, jitter_range)
            delay = max(0.5, delay)

        return round(delay, 2)

    def get_diagnostics(self) -> dict:
        """Return diagnostic telemetry snapshot."""
        now = datetime.now(timezone.utc)
        uptime_seconds = (
            (now - self.connection_started_at).total_seconds()
            if self.connection_started_at and self.state == ConnectionState.CONNECTED
            else None
        )
        data_lag_seconds = (
            (now - self.last_message_at).total_seconds()
            if self.last_message_at
            else None
        )

        return {
            "provider": self.provider,
            "state": self.state.value,
            "is_token_valid": not self.is_token_expired(),
            "connection_started_at": self.connection_started_at.isoformat() if self.connection_started_at else None,
            "uptime_seconds": uptime_seconds,
            "last_message_at": self.last_message_at.isoformat() if self.last_message_at else None,
            "last_heartbeat_at": self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
            "data_lag_seconds": round(data_lag_seconds, 2) if data_lag_seconds is not None else None,
            "reconnect_count": self.reconnect_count,
            "subscription_count": self.subscription_count,
            "last_error": self.last_error,
        }
