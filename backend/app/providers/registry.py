from app.providers.base import MarketDataProvider
from app.providers.fyers import FyersProvider
from app.providers.upstox import UpstoxProvider
from app.providers.groww import GrowwProvider
from app.providers.kotak_neo import KotakNeoProvider
from app.providers.binance_provider import BinanceProvider
from app.core.config import settings
import structlog

logger = structlog.get_logger()

INDIAN_PROVIDERS = ("fyers", "upstox", "groww", "kotak_neo")
CRYPTO_PROVIDERS = ("binance",)

_provider_instance: MarketDataProvider | None = None


def get_provider() -> MarketDataProvider:
    """Get the configured market data provider (singleton).

    Provider selection is gated by `api_type`:
      - "indian"  → fyers | upstox | groww | kotak_neo
      - "crypto"  → binance
    """
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = _create_provider()
    return _provider_instance


def reset_provider() -> None:
    """Drop the cached provider (used by tests / settings reload)."""
    global _provider_instance
    _provider_instance = None


def _create_provider() -> MarketDataProvider:
    """Create the market data provider based on configuration."""
    provider_name = settings.market_data_provider
    api_type = settings.api_type

    if api_type == "crypto":
        if provider_name != "binance":
            logger.warning(
                "api_type_crypto_fallback",
                requested=provider_name,
                using="binance",
            )
            provider_name = "binance"
    else:
        if provider_name not in INDIAN_PROVIDERS:
            logger.warning(
                "api_type_indian_fallback",
                requested=provider_name,
                using="fyers",
            )
            provider_name = "fyers"

    if provider_name == "fyers":
        logger.info("provider_init", api_type=api_type, provider="fyers")
        return FyersProvider()
    if provider_name == "upstox":
        logger.info("provider_init", api_type=api_type, provider="upstox")
        return UpstoxProvider()
    if provider_name == "groww":
        logger.info("provider_init", api_type=api_type, provider="groww")
        return GrowwProvider()
    if provider_name == "kotak_neo":
        logger.info("provider_init", api_type=api_type, provider="kotak_neo")
        return KotakNeoProvider()
    if provider_name == "binance":
        logger.info("provider_init", api_type=api_type, provider="binance")
        return BinanceProvider()

    raise ValueError(f"Unknown market data provider: {provider_name}")
