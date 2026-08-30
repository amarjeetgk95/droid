import pytest
from datetime import datetime, timezone, timedelta
from app.core.token_manager import TokenManager, ConnectionState, TokenInfo


class TestTokenManager:
    def setup_method(self):
        self.tm = TokenManager(provider="test", initial_backoff=1.0, max_backoff=60.0, enable_jitter=False)

    def test_initial_state_disconnected(self):
        assert self.tm.state == ConnectionState.DISCONNECTED
        assert self.tm.is_token_expired() is True

    def test_state_transitions(self):
        self.tm.set_state(ConnectionState.CONNECTING)
        assert self.tm.state == ConnectionState.CONNECTING

        self.tm.set_state(ConnectionState.CONNECTED)
        assert self.tm.state == ConnectionState.CONNECTED
        assert self.tm.connection_started_at is not None

    def test_exponential_backoff_calculation(self):
        # 1st attempt: 1.0s
        d1 = self.tm.record_reconnect_attempt()
        assert d1 == 1.0
        assert self.tm.state == ConnectionState.RECONNECTING

        # 2nd attempt: 2.0s
        d2 = self.tm.record_reconnect_attempt()
        assert d2 == 2.0

        # 3rd attempt: 4.0s
        d3 = self.tm.record_reconnect_attempt()
        assert d3 == 4.0

        # Max backoff clamp
        for _ in range(10):
            self.tm.record_reconnect_attempt()
        assert self.tm.record_reconnect_attempt() == 60.0

    def test_heartbeat_and_message_telemetry(self):
        self.tm.record_heartbeat()
        self.tm.record_message()
        diag = self.tm.get_diagnostics()
        assert diag["last_heartbeat_at"] is not None
        assert diag["last_message_at"] is not None

    @pytest.mark.asyncio
    async def test_token_refresh_flow(self):
        refreshed = False

        async def mock_refresh():
            nonlocal refreshed
            refreshed = True
            return TokenInfo(
                access_token="new-refreshed-token",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                provider="test",
            )

        self.tm.register_refresh_callback(mock_refresh)
        # Set expired token
        self.tm.set_token(TokenInfo(
            access_token="old-token",
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),
            provider="test",
        ))

        token = await self.tm.get_valid_token()
        assert token == "new-refreshed-token"
        assert refreshed is True
        assert self.tm.is_token_expired() is False
