from app.providers.base import MarketDataProvider
from app.providers.registry import get_provider
from app.models.market import (
    NormalizedQuote, NormalizedCandle, NormalizedOptionQuote, IndexCard,
    MarketHealthStatus, MarketStatusResponse, MarketBreadthData,
    DataStatus,
)
from app.core.circuit_breaker import CircuitBreaker
from app.core.cache import cache_service
from app.core.config import settings
from app.services.market_data_coordinator import market_data_coordinator
from datetime import datetime, timezone
import asyncio
import time
import structlog

logger = structlog.get_logger()


# ── Shared candle cache (module-level so every MarketService instance sees it) ──
#
# Why this exists: the signal scanner fans out 3 underlyings x 4 timeframes
# every 10s, and the intraday desk re-requests the same bars 30s later. That
# is ~216 FYERS calls/min from scanning alone, which overruns the provider
# rate budget and provokes HTTP 429. The 15m/1h bars are identical across
# those calls, so coalescing them removes most of the load rather than
# merely absorbing it.
#
# Invariants:
#   * ONLY non-empty results are cached. Caching a failed fetch would turn a
#     transient provider error into a TTL-long phantom "market closed".
#   * Explicit start/end range queries bypass the cache entirely — those are
#     historical/replay reads, not the live path this cache exists to protect.
_CANDLE_TTL_SECONDS: dict[str, float] = {
    "1m": 5.0, "3m": 5.0,
    "5m": 15.0, "15m": 15.0, "30m": 15.0,
    "1h": 30.0, "4h": 30.0,
    "1D": 300.0, "1W": 300.0,
}
_candle_cache: dict[tuple[str, str], tuple[float, list]] = {}
_candle_inflight: dict[tuple[str, str], "asyncio.Future[list]"] = {}
_CANDLE_CACHE_MAX_ENTRIES = 256


def _candle_cache_store(key: tuple[str, str], value: list) -> None:
    """Insert into the shared candle cache, evicting the oldest entry if full."""
    if len(_candle_cache) >= _CANDLE_CACHE_MAX_ENTRIES and key not in _candle_cache:
        oldest = min(_candle_cache.items(), key=lambda kv: kv[1][0])[0]
        _candle_cache.pop(oldest, None)
    _candle_cache[key] = (time.monotonic(), list(value))


class MarketService:
    """Service layer for market data operations.
    
    Protected by 3-State Circuit Breaker and Unified Cache Layer.
    Sits between API routes and provider abstraction.
    """

    def __init__(self, provider: MarketDataProvider | None = None):
        # NOTE: the provider singleton is resolved LAZILY (see _provider
        # property). Capturing get_provider() here froze long-lived owners
        # (e.g. the module-level tactical_horizon_engine) onto a stale
        # FyersProvider after restart_provider_stream() rotated the singleton
        # on OAuth re-auth — quotes kept working via fresh per-request
        # services while every forecast fan-out silently hit the old token
        # and returned [] ("Insufficient ... candle data"). An explicit
        # provider (tests, callers) still wins and is never re-resolved.
        self._explicit_provider = provider
        try:
            _name = provider.provider_name if provider is not None else "fyers"
        except Exception:
            _name = "fyers"
        self._circuit_breaker = CircuitBreaker(
            name=_name,
            failure_threshold=settings.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=settings.circuit_breaker_recovery_timeout_seconds,
            half_open_success_threshold=settings.circuit_breaker_half_open_success_threshold,
        )

    @property
    def _provider(self) -> MarketDataProvider:
        if self._explicit_provider is not None:
            return self._explicit_provider
        return get_provider()

    @_provider.setter
    def _provider(self, value: MarketDataProvider | None) -> None:
        self._explicit_provider = value

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
        if symbol_upper not in symbol_map and not any(k in symbol_upper for k in ("NIFTY", "SENSEX", "BANK", "FIN", "VIX", "BTC", "ETH", "SOL")):
            raise ValueError(f"Invalid or unsupported symbol: {symbol}")
        resolved = symbol_map.get(symbol_upper, symbol)

        async def _fetch():
            async def _raw_fetch():
                return await self._provider.get_quote(resolved)

            return await self._circuit_breaker.call(_raw_fetch)

        val = await market_data_coordinator.get_or_compute(
            f"quote:{resolved}",
            _fetch,
            source_name=self._provider.provider_name,
        )
        return val.data

    async def get_quotes(self) -> list[NormalizedQuote]:
        async def _fetch():
            return await self._circuit_breaker.call(
                self._provider.get_quotes,
                fallback=lambda: [],
            )

        val = await market_data_coordinator.get_or_compute(
            "quotes",
            _fetch,
            source_name=self._provider.provider_name,
        )
        return val.data or []

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

        ttl = _CANDLE_TTL_SECONDS.get(timeframe, 15.0)
        # Historical/replay reads must never observe a live-cache entry.
        if start is not None or end is not None:
            return await self._fetch_candles_uncached(resolved, timeframe, start, end)

        key = (resolved, timeframe)
        cached = _candle_cache.get(key)
        if cached is not None:
            ts, value = cached
            if (time.monotonic() - ts) <= ttl:
                return list(value)
            _candle_cache.pop(key, None)

        # Single-flight: concurrent callers for the same bars share one HTTP
        # call. The scanner gathers underlyings in parallel and the dashboard
        # polls on its own timer, so without this the same 1m NIFTY series is
        # requested several times inside one bar.
        inflight = _candle_inflight.get(key)
        if inflight is not None:
            try:
                return list(await asyncio.shield(inflight))
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # fall through and fetch independently

        loop = asyncio.get_running_loop()
        future: asyncio.Future[list] = loop.create_future()
        _candle_inflight[key] = future
        try:
            value = await self._fetch_candles_uncached(resolved, timeframe, start, end)
        except BaseException as exc:
            if not future.done():
                future.set_exception(exc)
            raise
        else:
            # Never cache a failure — an empty list means "provider said
            # nothing", not "there is genuinely no data".
            if value:
                _candle_cache_store(key, value)
            if not future.done():
                future.set_result(list(value))
            return list(value)
        finally:
            _candle_inflight.pop(key, None)

    async def _fetch_candles_uncached(
        self,
        resolved: str,
        timeframe: str,
        start: datetime | None,
        end: datetime | None,
    ) -> list[NormalizedCandle]:
        return await self._circuit_breaker.call(
            lambda: self._provider.get_candles(resolved, timeframe, start, end),
            fallback=lambda: [],
        )

    async def fetch_index_cards_raw(self) -> list[IndexCard]:
        return await self._circuit_breaker.call(
            self._provider.get_index_cards,
            fallback=lambda: [],
        )

    async def get_index_cards(self) -> list[IndexCard]:
        val = await market_data_coordinator.get_or_compute(
            "cards",
            self.fetch_index_cards_raw,
            source_name=self._provider.provider_name,
        )
        return val.data or []

    async def fetch_market_status_raw(self) -> MarketStatusResponse:
        return await self._provider.get_market_status()

    async def get_market_status(self) -> MarketStatusResponse:
        val = await market_data_coordinator.get_or_compute(
            "status",
            self.fetch_market_status_raw,
            source_name=self._provider.provider_name,
        )
        return val.data

    async def fetch_market_breadth_raw(self) -> MarketBreadthData:
        return await self._circuit_breaker.call(
            self._provider.get_market_breadth,
            fallback=lambda: MarketBreadthData(
                advancing=0,
                declining=0,
                unchanged=0,
                advance_decline_ratio=0.0,
                sentiment="NEUTRAL",
                sentiment_score=50.0,
                status=DataStatus.OFFLINE,
                timestamp=datetime.now(timezone.utc),
            ),
        )

    async def get_market_breadth(self) -> MarketBreadthData:
        val = await market_data_coordinator.get_or_compute(
            "breadth",
            self.fetch_market_breadth_raw,
            source_name=self._provider.provider_name,
        )
        return val.data

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

    async def fetch_health_raw(self) -> MarketHealthStatus:
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

    async def get_health(self) -> MarketHealthStatus:
        val = await market_data_coordinator.get_or_compute(
            "health",
            self.fetch_health_raw,
            source_name=self._provider.provider_name,
        )
        if val.data is None:
            return await self.fetch_health_raw()
        return val.data
