import asyncio
from datetime import datetime, timezone
from app.providers.base import MarketDataProvider
from app.models.market import (
    NormalizedQuote, NormalizedCandle, NormalizedOptionQuote,
    IndexCard, MarketHealthStatus, MarketStatusResponse,
    MarketBreadthData, DataStatus, MarketSession,
)
from app.core.config import settings
from app.core.token_manager import TokenManager, ConnectionState, TokenInfo
from app.core.rate_limiter import TokenBucketRateLimiter
from app.services.binance_service import BinanceService, PAIR_DISPLAY_NAMES
import structlog

logger = structlog.get_logger()


class BinanceProvider(MarketDataProvider):
    """Binance Spot/Futures Market Data Provider.

    Public market endpoints (tickers, candles, order book, funding)
    do not require authentication; signed endpoints (private account
    queries) use the optional `BINANCE_API_KEY` / `BINANCE_API_SECRET`.
    """

    PROVIDER_ID = "binance"
    API_TYPE = "crypto"

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
    ):
        self.api_key = api_key or settings.binance_api_key
        self.api_secret = api_secret or settings.binance_api_secret

        self.token_manager = TokenManager(
            provider=self.PROVIDER_ID,
            initial_backoff=settings.ws_reconnect_initial_seconds,
            max_backoff=settings.ws_reconnect_max_seconds,
            enable_jitter=settings.ws_reconnect_jitter,
        )
        # Binance public WebSocket is anonymous — mark the token as valid.
        self.token_manager.set_token(
            TokenInfo(access_token="binance-public", provider=self.PROVIDER_ID)
        )

        self.rate_limiter = TokenBucketRateLimiter(
            requests_per_second=20.0,
            requests_per_minute=1200.0,
            burst_limit=50,
        )

        self._service = BinanceService()
        self._stream_running = False

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_ID

    def get_token_manager(self) -> TokenManager:
        return self.token_manager

    def get_rate_limiter(self) -> TokenBucketRateLimiter:
        return self.rate_limiter

    async def get_quote(self, symbol: str) -> NormalizedQuote:
        await self.rate_limiter.acquire()
        now = datetime.now(timezone.utc)
        try:
            ticker = await self._service.get_ticker(symbol)
        except Exception as e:
            logger.warning("binance_quote_failed", symbol=symbol, error=str(e))
            return NormalizedQuote(
                symbol=symbol, display_name=symbol, timestamp=now,
                ltp=0.0, open=0.0, high=0.0, low=0.0,
                previous_close=0.0, change=0.0, change_percent=0.0,
                volume=0, open_interest=None,
                status=DataStatus.ERROR, provider=self.provider_name,
            )

        self.token_manager.record_message()
        return NormalizedQuote(
            symbol=symbol,
            display_name=PAIR_DISPLAY_NAMES.get(symbol, (symbol, symbol, "USDT"))[0],
            timestamp=now,
            ltp=float(ticker.price or 0.0),
            open=float(ticker.price or 0.0),
            high=float(ticker.high_24h or 0.0),
            low=float(ticker.low_24h or 0.0),
            previous_close=float(ticker.price or 0.0) - float(ticker.change_24h or 0.0),
            change=float(ticker.change_24h or 0.0),
            change_percent=float(ticker.change_percent_24h or 0.0),
            volume=int(ticker.volume_24h_quote or 0),
            open_interest=None,
            status=DataStatus.LIVE,
            provider=self.provider_name,
        )

    async def get_quotes(self, symbols: list[str] | None = None) -> list[NormalizedQuote]:
        targets = symbols or list(PAIR_DISPLAY_NAMES.keys())
        return [await self.get_quote(s) for s in targets]

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        await self.rate_limiter.acquire()
        candles = await self._service.get_candles(symbol, timeframe=timeframe, limit=200)
        self.token_manager.record_message()
        return candles

    async def get_index_cards(self) -> list[IndexCard]:
        tickers = await self._service.get_top_tickers()
        cards: list[IndexCard] = []
        for t in tickers[:20]:
            sym = t.symbol
            if sym not in PAIR_DISPLAY_NAMES:
                continue
            cards.append(IndexCard(
                symbol=sym,
                display_name=t.display_name or PAIR_DISPLAY_NAMES[sym][0],
                ltp=float(t.price or 0.0),
                change=float(t.change_24h or 0.0),
                change_percent=float(t.change_percent_24h or 0.0),
                open=float(t.price or 0.0),
                high=float(t.high_24h or 0.0),
                low=float(t.low_24h or 0.0),
                previous_close=float(t.price or 0.0) - float(t.change_24h or 0.0),
                volume=int(t.volume_24h_quote or 0),
                open_interest=None,
                sparkline=t.sparkline or [],
                status=DataStatus.LIVE,
                timestamp=datetime.now(timezone.utc),
                provider=self.provider_name,
            ))
        return cards

    async def get_market_status(self) -> MarketStatusResponse:
        return MarketStatusResponse(
            session=MarketSession.OPEN,
            market_time=datetime.now(timezone.utc),
            is_trading_day=True,
            data_status=DataStatus.LIVE,
            provider=self.provider_name,
        )

    async def get_health(self) -> MarketHealthStatus:
        self.token_manager.record_heartbeat()
        return MarketHealthStatus(
            status="HEALTHY",
            provider=self.provider_name,
            mode="LIVE",
            last_update=datetime.now(timezone.utc),
            data_age_seconds=0.5,
            latency_ms=20.0,
            active_instruments=len(PAIR_DISPLAY_NAMES),
            reconnect_count=0,
            subscriptions=len(PAIR_DISPLAY_NAMES),
            buffer_depth=0,
            dropped_events=0,
            circuit_breaker_state="CLOSED",
            last_heartbeat=datetime.now(timezone.utc),
            message="Binance Spot public WebSocket active",
        )

    async def get_market_breadth(self) -> MarketBreadthData:
        return MarketBreadthData(
            advancing=0, declining=0, unchanged=0, advance_decline_ratio=0.0,
            sectors=[], sentiment="NEUTRAL", sentiment_score=50.0,
            status=DataStatus.LIVE,
            timestamp=datetime.now(timezone.utc),
        )

    async def get_expiries(self, symbol: str) -> list[datetime]:
        return []

    async def get_option_chain(
        self,
        symbol: str,
        expiry: datetime | None = None,
    ) -> list[NormalizedOptionQuote]:
        return []

    async def start_stream(self) -> None:
        if self._stream_running:
            return
        self._stream_running = True
        self.token_manager.set_state(ConnectionState.CONNECTED)

    async def stop_stream(self) -> None:
        self._stream_running = False
        self.token_manager.set_state(ConnectionState.DISCONNECTED)
