import asyncio
import hashlib
import hmac
import time
from datetime import datetime, timezone
from typing import Literal
from app.providers.base import MarketDataProvider
from app.models.market import (
    NormalizedQuote, NormalizedCandle, NormalizedOptionQuote,
    IndexCard, MarketHealthStatus, MarketStatusResponse,
    MarketBreadthData, DataStatus, MarketSession,
)
from app.core.config import settings
from app.core.token_manager import TokenManager, ConnectionState, TokenInfo
from app.core.rate_limiter import TokenBucketRateLimiter
from app.services.calendar_service import calendar_service
import structlog

logger = structlog.get_logger()


class GrowwProvider(MarketDataProvider):
    """Groww Open API Market Data Provider Adapter.

    Auth: API Key + API Secret (checksum flow) or API Key + TOTP.
    Access token is short-lived (~1 day) and requires daily re-approval via the
    Groww Cloud API Keys page (https://groww.in/trade-api/api-keys).
    """

    PROVIDER_ID = "groww"
    API_BASE = "https://api.groww.in/v1"
    AUTH_ENDPOINT = "/token/api/access"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        access_token: str | None = None,
        auth_mode: Literal["checksum", "totp"] = "checksum",
    ):
        self.api_key = api_key or settings.groww_api_key
        self.api_secret = api_secret or settings.groww_api_secret
        self.auth_mode = auth_mode or settings.groww_auth_mode

        self.token_manager = TokenManager(
            provider=self.PROVIDER_ID,
            initial_backoff=settings.ws_reconnect_initial_seconds,
            max_backoff=settings.ws_reconnect_max_seconds,
            enable_jitter=settings.ws_reconnect_jitter,
        )
        if access_token or settings.groww_access_token:
            self.token_manager.set_token(
                TokenInfo(
                    access_token=access_token or settings.groww_access_token,
                    provider=self.PROVIDER_ID,
                )
            )

        self.rate_limiter = TokenBucketRateLimiter(
            requests_per_second=settings.rate_limit_requests_per_second,
            requests_per_minute=settings.rate_limit_requests_per_minute,
            burst_limit=settings.rate_limit_burst_limit,
        )

        self.token_manager.register_refresh_callback(self._refresh_callback)
        self._stream_running = False
        self._stream_task: asyncio.Task | None = None

        # Groww uses its own symbol map; these are the canonical trading symbols.
        self.symbol_map = {
            "NIFTY 50":   {"exchange": "NSE", "segment": "CASH", "trading_symbol": "NIFTY"},
            "BANKNIFTY":  {"exchange": "NSE", "segment": "CASH", "trading_symbol": "BANKNIFTY"},
            "FINNIFTY":   {"exchange": "NSE", "segment": "CASH", "trading_symbol": "FINNIFTY"},
            "SENSEX":     {"exchange": "BSE", "segment": "CASH", "trading_symbol": "SENSEX"},
            "INDIA VIX":  {"exchange": "NSE", "segment": "CASH", "trading_symbol": "INDIAVIX"},
        }

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_ID

    def get_token_manager(self) -> TokenManager:
        return self.token_manager

    def get_rate_limiter(self) -> TokenBucketRateLimiter:
        return self.rate_limiter

    def _generate_checksum(self, timestamp: str) -> str:
        """SHA256(secret + timestamp) as per Groww spec."""
        return hashlib.sha256((self.api_secret + timestamp).encode("utf-8")).hexdigest()

    async def _fetch_access_token(self) -> str | None:
        """Obtain a short-lived access token using the configured auth mode."""
        if not self.api_key or not self.api_secret:
            return None

        import httpx
        timestamp = str(int(time.time()))
        url = f"{self.API_BASE}{self.AUTH_ENDPOINT}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        if self.auth_mode == "checksum":
            checksum = self._generate_checksum(timestamp)
            payload = {"key_type": "approval", "checksum": checksum, "timestamp": timestamp}
        else:  # totp
            # TOTP mode requires user to provide TOTP code externally
            # Here we just return None — caller must supply totp via settings
            return None

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    token = data.get("token") or data.get("access_token")
                    if token:
                        return token
                logger.warning("groww_token_failed", status=resp.status_code, text=resp.text[:200])
        except Exception as e:
            logger.warning("groww_token_exception", error=str(e))
        return None

    def _has_valid_credentials(self) -> bool:
        return bool(self.token_manager.token_info and self.token_manager.token_info.access_token)

    async def _refresh_callback(self) -> TokenInfo:
        """Refresh callback (registered on the token manager). Fetches a fresh
        Groww access token via the checksum/TOTP flow and persists it."""
        token = await self._fetch_access_token()
        if not token:
            raise RuntimeError("Groww token refresh failed (missing credentials or non-200 response)")
        info = TokenInfo(access_token=token, provider=self.PROVIDER_ID)
        self.token_manager.set_token(info)
        return info

    async def get_quote(self, symbol: str) -> NormalizedQuote:
        await self.rate_limiter.acquire()
        try:
            token = await self.token_manager.get_valid_token()
        except RuntimeError:
            token = ""
        now = datetime.now(timezone.utc)
        self.token_manager.record_message()

        # In stub mode, return zeros when no token
        if not token:
            return NormalizedQuote(
                symbol=symbol,
                display_name=symbol,
                timestamp=now,
                ltp=0.0,
                open=0.0,
                high=0.0,
                low=0.0,
                previous_close=0.0,
                change=0.0,
                change_percent=0.0,
                volume=0,
                open_interest=None if "VIX" in symbol else 0,
                status=DataStatus.DISCONNECTED,
                provider=self.provider_name,
            )

        # TODO: Implement real quote fetch with Authorization: Bearer <token> + X-API-VERSION: 1.0
        return NormalizedQuote(
            symbol=symbol,
            display_name=symbol,
            timestamp=now,
            ltp=0.0,
            open=0.0,
            high=0.0,
            low=0.0,
            previous_close=0.0,
            change=0.0,
            change_percent=0.0,
            volume=0,
            open_interest=None if "VIX" in symbol else 0,
            status=DataStatus.LIVE,
            provider=self.provider_name,
        )

    async def get_quotes(self, symbols: list[str] | None = None) -> list[NormalizedQuote]:
        targets = symbols or list(self.symbol_map.keys())
        return [await self.get_quote(s) for s in targets]

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        await self.rate_limiter.acquire()
        now = datetime.now(timezone.utc)
        count = 75 if timeframe == "5m" else 30
        return [
            NormalizedCandle(
                timestamp=now,
                open=0.0, high=0.0, low=0.0, close=0.0,
                volume=0, vwap=None,
            )
            for _ in range(count)
        ]

    async def get_index_cards(self) -> list[IndexCard]:
        quotes = await self.get_quotes()
        return [
            IndexCard(
                symbol=q.symbol,
                display_name=q.display_name,
                ltp=q.ltp,
                change=q.change,
                change_percent=q.change_percent,
                open=q.open,
                high=q.high,
                low=q.low,
                previous_close=q.previous_close,
                volume=q.volume,
                open_interest=q.open_interest,
                sparkline=[q.previous_close, q.ltp],
                status=q.status,
                timestamp=q.timestamp,
                provider=self.provider_name,
            )
            for q in quotes
        ]

    async def get_market_status(self) -> MarketStatusResponse:
        now = datetime.now(timezone.utc)
        is_trading = calendar_service.is_trading_day(now.date())
        return MarketStatusResponse(
            session=MarketSession.OPEN if is_trading else MarketSession.CLOSED,
            market_time=now,
            is_trading_day=is_trading,
            data_status=DataStatus.LIVE if self._has_valid_credentials() else DataStatus.DISCONNECTED,
            provider=self.provider_name,
        )

    async def get_health(self) -> MarketHealthStatus:
        self.token_manager.record_heartbeat()
        diag = self.token_manager.get_diagnostics()

        return MarketHealthStatus(
            status="HEALTHY" if diag["is_token_valid"] else "DEGRADED",
            provider=self.provider_name,
            mode="LIVE" if diag["is_token_valid"] else "DEMO",
            last_update=datetime.now(timezone.utc),
            data_age_seconds=diag["data_lag_seconds"] or 0.5,
            latency_ms=40.0,
            active_instruments=len(self.symbol_map),
            reconnect_count=diag["reconnect_count"],
            subscriptions=len(self.symbol_map),
            buffer_depth=0,
            dropped_events=0,
            circuit_breaker_state="CLOSED",
            last_heartbeat=datetime.now(timezone.utc),
            message="Groww Open API connected" if diag["is_token_valid"] else "Awaiting Groww access token (checksum/TOTP flow)",
        )

    async def get_market_breadth(self) -> MarketBreadthData:
        return MarketBreadthData(
            advancing=0, declining=0, unchanged=0, advance_decline_ratio=0.0,
            sectors=[], sentiment="NEUTRAL", sentiment_score=50.0,
            status=DataStatus.DISCONNECTED,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_expiries(self, symbol: str) -> list[datetime]:
        from app.services.contract_master import contract_master_service
        underlying = "NIFTY"
        if "BANK" in symbol:
            underlying = "BANKNIFTY"
        dates = contract_master_service.get_expiries(underlying)
        return [datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc) for d in dates]

    async def get_option_chain(
        self,
        symbol: str,
        expiry: datetime | None = None,
    ) -> list[NormalizedOptionQuote]:
        await self.rate_limiter.acquire()
        return []

    async def start_stream(self) -> None:
        if self._stream_running:
            return
        self._stream_running = True
        self.token_manager.set_state(ConnectionState.CONNECTED)
        logger.info("groww_stream_started")

    async def stop_stream(self) -> None:
        self._stream_running = False
        self.token_manager.set_state(ConnectionState.DISCONNECTED)
        if self._stream_task:
            self._stream_task.cancel()
        logger.info("groww_stream_stopped")
