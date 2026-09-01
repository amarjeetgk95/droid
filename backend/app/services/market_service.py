from app.providers.base import MarketDataProvider
from app.providers.registry import get_provider
from app.models.market import (
    NormalizedQuote, NormalizedCandle, NormalizedOptionQuote, IndexCard,
    MarketHealthStatus, MarketStatusResponse, MarketBreadthData,
    DataStatus,
)
from app.core.circuit_breaker import CircuitBreaker, CircuitState
from app.core.cache import cache_service
from app.core.config import settings
from datetime import datetime, timezone
import structlog

logger = structlog.get_logger()


class MarketService:
    """Service layer for market data operations.
    
    Protected by 3-State Circuit Breaker and Unified Cache Layer.
    Sits between API routes and provider abstraction.
    """

    def __init__(self, provider: MarketDataProvider | None = None):
        self._provider = provider or get_provider()
        self._circuit_breaker = CircuitBreaker(
            name=self._provider.provider_name,
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=settings.circuit_breaker_recovery_timeout_seconds,
            half_open_success_threshold=settings.circuit_breaker_half_open_success_threshold,
        )

    @property
    def circuit_breaker(self) -> CircuitBreaker:
        return self._circuit_breaker

    async def get_quote(self, symbol: str) -> NormalizedQuote:
        symbol_upper = symbol.upper().replace(" ", "")
        symbol_map = {
            "NIFTY": "NIFTY 50",
            "NIFTY50": "NIFTY 50",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "SENSEX": "SENSEX",
            "BSESENSEX": "SENSEX",
            "VIX": "INDIA VIX",
            "INDIAVIX": "INDIA VIX",
        }
        resolved = symbol_map.get(symbol_upper, symbol)

        async def _fetch():
            return await self._provider.get_quote(resolved)

        def _fallback():
            return NormalizedQuote(
                symbol=resolved,
                display_name=resolved,
                timestamp=datetime.now(timezone.utc),
                ltp=25000.0,
                open=24950.0,
                high=25050.0,
                low=24900.0,
                previous_close=24900.0,
                change=100.0,
                change_percent=0.4,
                volume=100000,
                status=DataStatus.OFFLINE,
                provider="fallback",
            )

        return await self._circuit_breaker.call(_fetch, fallback=_fallback)

    async def get_quotes(self) -> list[NormalizedQuote]:
        return await self._circuit_breaker.call(
            self._provider.get_quotes,
            fallback=lambda: [],
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        # Canonical 6-TF Chart Analysis + legacy aliases
        valid_timeframes = ["1m", "5m", "15m", "1h", "4h", "1D", "1d", "30m", "1W"]
        tf_norm = timeframe.strip()
        # Normalize Daily case
        if tf_norm == "1d":
            tf_norm = "1D"
        if tf_norm not in valid_timeframes and tf_norm not in ["1m","5m","15m","1h","4h","1D"]:
            raise ValueError(f"Invalid timeframe: {timeframe}. Must be one of {valid_timeframes}")
        timeframe = tf_norm
        symbol_upper = symbol.upper().replace(" ", "")
        symbol_map = {
            "NIFTY": "NIFTY 50",
            "NIFTY50": "NIFTY 50",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "SENSEX": "SENSEX",
            "BSESENSEX": "SENSEX",
            "VIX": "INDIA VIX",
            "INDIAVIX": "INDIA VIX",
        }
        resolved = symbol_map.get(symbol_upper, symbol)
        return await self._circuit_breaker.call(
            lambda: self._provider.get_candles(resolved, timeframe, start, end),
            fallback=lambda: [],
        )

    async def get_index_cards(self) -> list[IndexCard]:
        return await self._circuit_breaker.call(
            self._provider.get_index_cards,
            fallback=lambda: [],
        )

    async def get_market_status(self) -> MarketStatusResponse:
        return await self._provider.get_market_status()

    async def get_market_breadth(self) -> MarketBreadthData:
        return await self._circuit_breaker.call(
            self._provider.get_market_breadth,
            fallback=lambda: MarketBreadthData(
                advancing=250,
                declining=250,
                unchanged=0,
                advance_decline_ratio=1.0,
                sentiment="NEUTRAL",
                sentiment_score=50.0,
                status=DataStatus.OFFLINE,
                timestamp=datetime.now(timezone.utc),
            ),
        )

    async def get_option_chain(
        self,
        symbol: str,
        expiry: datetime | None = None,
    ) -> list[NormalizedOptionQuote]:
        symbol_upper = symbol.upper().replace(" ", "")
        symbol_map = {
            "NIFTY": "NIFTY",
            "NIFTY50": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "SENSEX": "SENSEX",
            "BSESENSEX": "SENSEX",
        }
        resolved = symbol_map.get(symbol_upper, symbol)
        expiry_key = expiry.isoformat() if expiry else "latest"
        
        # Check cache
        cached = await cache_service.get_option_chain_snapshot(resolved, expiry_key)
        if cached is not None:
            return [NormalizedOptionQuote(**item) for item in cached]

        chain = await self._provider.get_option_chain(resolved, expiry)
        await cache_service.set_option_chain_snapshot(
            resolved,
            expiry_key,
            [q.model_dump(mode="json") for q in chain],
            ttl_seconds=5.0,
        )
        return chain

    async def get_expiries(self, symbol: str) -> list[datetime]:
        symbol_upper = symbol.upper().replace(" ", "")
        symbol_map = {
            "NIFTY": "NIFTY",
            "NIFTY50": "NIFTY",
            "BANKNIFTY": "BANKNIFTY",
            "FINNIFTY": "FINNIFTY",
            "SENSEX": "SENSEX",
            "BSESENSEX": "SENSEX",
        }
        resolved = symbol_map.get(symbol_upper, symbol)
        return await self._provider.get_expiries(resolved)

    async def get_health(self) -> MarketHealthStatus:
        from app.services.event_buffer import event_buffer
        health = await self._provider.get_health()
        buf_health = event_buffer.health()
        cb_status = self._circuit_breaker.get_status()

        return MarketHealthStatus(
            status="UNHEALTHY" if cb_status["state"] == "OPEN" else health.status,
            provider=health.provider,
            mode=health.mode,
            last_update=health.last_update,
            data_age_seconds=health.data_age_seconds,
            latency_ms=health.latency_ms,
            active_instruments=health.active_instruments,
            reconnect_count=health.reconnect_count,
            subscriptions=health.subscriptions,
            buffer_depth=buf_health["depth"],
            dropped_events=buf_health["total_dropped"],
            circuit_breaker_state=cb_status["state"],
            last_heartbeat=health.last_heartbeat,
            message=f"Circuit Breaker: {cb_status['state']} | {health.message}",
        )
