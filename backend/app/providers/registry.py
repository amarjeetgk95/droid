from app.providers.base import MarketDataProvider
from app.providers.mock import MockProvider
from app.providers.fyers import FyersProvider
from app.providers.upstox import UpstoxProvider
from app.core.config import settings
import structlog

logger = structlog.get_logger()

_provider_instance: MarketDataProvider | None = None

def get_provider() -> MarketDataProvider:
    """Get the configured market data provider (singleton)."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = _create_provider()
    return _provider_instance

def _create_provider() -> MarketDataProvider:
    """Create the market data provider based on configuration."""
    provider_name = settings.market_data_provider
    
    if provider_name == "mock":
        logger.info("provider_init", provider="mock", mode=settings.mock_data_mode, seed=settings.mock_seed)
        return MockProvider(
            mode=settings.mock_data_mode,
            seed=settings.mock_seed,
        )
    elif provider_name == "fyers":
        logger.info("provider_init", provider="fyers")
        return FyersProvider()
    elif provider_name == "upstox":
        logger.info("provider_init", provider="upstox")
        return UpstoxProvider()
    else:
        raise ValueError(f"Unknown market data provider: {provider_name}")
