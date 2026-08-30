from app.providers.base import MarketDataProvider
from app.providers.fyers import FyersProvider
from app.providers.upstox import UpstoxProvider
from app.providers.groww import GrowwProvider
from app.providers.kotak_neo import KotakNeoProvider
from app.providers.binance_provider import BinanceProvider
from app.core.broker_runtime import get_config
import structlog

logger = structlog.get_logger()

INDIAN_PROVIDERS = ("fyers", "upstox", "groww", "kotak_neo")
CRYPTO_PROVIDERS = ("binance",)

_provider_instance: MarketDataProvider | None = None


def get_provider() -> MarketDataProvider:
    """Get the configured market data provider (singleton).

    Provider selection is gated by api_type:
      - "indian"  -> fyers | upstox | groww | kotak_neo
      - "crypto"  -> binance

    The active provider comes from app.core.broker_runtime, which honors the
    saved user settings (app_settings.broker.provider) and falls back to the
    MARKET_DATA_PROVIDER env var. Credentials saved in the settings UI are
    injected into the provider so live data fetching activates (instead of
    always falling back to the DEMO provider).
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
    """Create the market data provider based on the runtime broker config.

    The runtime config (provider + api_type + credentials) is sourced from
    app.core.broker_runtime, populated from the persisted user settings and
    falling back to env-driven configuration. Invalid provider selections are
    normalized to a safe default (fyers for indian, binance for crypto) so the
    backend never crashes on startup.
    """
    cfg = get_config()
    provider_name = cfg.provider
    api_type = cfg.api_type

    if api_type == "crypto":
        if provider_name != "binance":
            logger.warning(
                "api_type_crypto_fallback",
                api_type=api_type,
                requested=provider_name,
                using="binance",
            )
            provider_name = "binance"
    else:
        if provider_name not in INDIAN_PROVIDERS:
            logger.warning(
                "api_type_indian_fallback",
                api_type=api_type,
                requested=provider_name,
                using="fyers",
            )
            provider_name = "fyers"

    creds = cfg.credentials or {}

    if provider_name == "fyers":
        logger.info("provider_init", api_type=api_type, provider="fyers", live=bool(creds))
        return FyersProvider(
            app_id=creds.get("app_id"),
            secret_key=creds.get("secret_key"),
            access_token=creds.get("access_token"),
        )
    if provider_name == "upstox":
        logger.info("provider_init", api_type=api_type, provider="upstox", live=bool(creds))
        return UpstoxProvider(
            api_key=creds.get("api_key"),
            secret_key=creds.get("secret_key"),
            access_token=creds.get("access_token"),
        )
    if provider_name == "groww":
        logger.info("provider_init", api_type=api_type, provider="groww", live=bool(creds))
        return GrowwProvider(
            api_key=creds.get("api_key"),
            api_secret=creds.get("api_secret"),
            access_token=creds.get("access_token"),
            auth_mode=creds.get("auth_mode") or "checksum",
        )
    if provider_name == "kotak_neo":
        logger.info("provider_init", api_type=api_type, provider="kotak_neo", live=bool(creds))
        return KotakNeoProvider(
            api_key=creds.get("api_key"),
            api_secret=creds.get("api_secret"),
            access_token=creds.get("access_token"),
            mobile_number=creds.get("mobile_number"),
            mpin=creds.get("mpin"),
            totp=creds.get("totp"),
        )
    if provider_name == "binance":
        logger.info("provider_init", api_type=api_type, provider="binance", live=bool(creds))
        return BinanceProvider(
            api_key=creds.get("api_key"),
            api_secret=creds.get("api_secret"),
        )

    raise ValueError(f"Unknown market data provider: {provider_name}")
