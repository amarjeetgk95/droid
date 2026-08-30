from abc import ABC, abstractmethod
from app.models.market import (
    NormalizedQuote, NormalizedCandle, NormalizedOptionQuote,
    MarketHealthStatus, MarketStatusResponse, IndexCard,
    MarketBreadthData,
)
from datetime import datetime


from app.core.token_manager import TokenManager
from app.core.rate_limiter import TokenBucketRateLimiter
from app.models.contracts import ContractMaster, TickEvent


class MarketDataProvider(ABC):
    """Abstract market data provider interface.
    
    All provider implementations (Mock, Fyers, Upstox) must conform
    to this interface. The quantitative engine and API layer depend
    only on these normalized methods — never on provider-specific
    response structures.
    """

    @abstractmethod
    async def get_quote(self, symbol: str) -> NormalizedQuote:
        """Get a normalized quote for a single symbol."""
        ...

    @abstractmethod
    async def get_quotes(self, symbols: list[str] | None = None) -> list[NormalizedQuote]:
        """Get normalized quotes for multiple symbols."""
        ...

    @abstractmethod
    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        start: datetime | None = None,
        end: datetime | None = None,
    ) -> list[NormalizedCandle]:
        """Get historical OHLCV candles for a symbol."""
        ...

    @abstractmethod
    async def get_index_cards(self) -> list[IndexCard]:
        """Get dashboard index card data for all tracked indices."""
        ...

    @abstractmethod
    async def get_market_status(self) -> MarketStatusResponse:
        """Get current market session status."""
        ...

    @abstractmethod
    async def get_health(self) -> MarketHealthStatus:
        """Get market data health information."""
        ...

    @abstractmethod
    async def get_market_breadth(self) -> MarketBreadthData:
        """Get market breadth data."""
        ...

    @abstractmethod
    async def get_option_chain(
        self,
        symbol: str,
        expiry: datetime | None = None,
    ) -> list[NormalizedOptionQuote]:
        """Get normalized option chain for a symbol."""
        ...

    @abstractmethod
    async def get_expiries(self, symbol: str) -> list[datetime]:
        """Get available expiries for a symbol."""
        ...

    @abstractmethod
    async def start_stream(self) -> None:
        """Connect to real-time upstream market feed."""
        ...

    @abstractmethod
    async def stop_stream(self) -> None:
        """Disconnect upstream market feed."""
        ...

    @abstractmethod
    def get_token_manager(self) -> TokenManager:
        """Get the token lifecycle manager for this provider."""
        ...

    @abstractmethod
    def get_rate_limiter(self) -> TokenBucketRateLimiter:
        """Get the API rate limiter for this provider."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the provider identifier."""
        ...
