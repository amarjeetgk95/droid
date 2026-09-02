from app.providers.base import MarketDataProvider
from app.providers.fyers import FyersProvider
from app.providers.flattrade import FlattradeProvider
from app.providers.binance_provider import BinanceProvider
from app.core.broker_runtime import get_config
import asyncio
import structlog

logger = structlog.get_logger()

INDIAN_PROVIDERS = ("fyers", "flattrade")
CRYPTO_PROVIDERS = ("binance",)

_provider_instance: MarketDataProvider | None = None
_previous_provider: MarketDataProvider | None = None
_stream_start_task: asyncio.Task | None = None
_suppress_autostart: bool = False


def _schedule_start_stream(provider: MarketDataProvider) -> None:
    """Schedule start_stream() on the running event loop.

    Safe to call only when an asyncio loop is running (i.e. inside a request).
    Centralized so providers are auto-started on first creation AND after
    reset_provider() (e.g. after Settings save). Without this, saving Groww
    creds created the GrowwProvider but its licensed stream was never started,
    so MARKET_TICKS stayed at 0.

    Suppressed by :func:`suppress_autostart` so explicit callers (e.g.
    ``main.py`` lifespan startup) don't race with a background auto-start task.
    """
    global _stream_start_task
    if _suppress_autostart:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No loop running (e.g. module import) — caller must trigger later
        logger.debug("registry_no_running_loop_skip_autostart", provider=provider.provider_name)
        return
    if _stream_start_task is not None and not _stream_start_task.done():
        # Already starting/stopping; let it finish
        return

    async def _runner():
        try:
            await provider.stop_stream()
        except Exception as e:
            logger.debug("registry_autostart_stop_old_failed", error=str(e)[:150])
        try:
            await provider.start_stream()
            logger.info("registry_autostart_stream_started", provider=provider.provider_name)
        except Exception as e:
            logger.warning("registry_autostart_stream_failed", provider=provider.provider_name, error=str(e)[:200])

    _stream_start_task = loop.create_task(_runner())


class _AutostartGuard:
    """Context manager that suppresses registry auto-start while held.

    Use during explicit ``await provider.start_stream()`` calls (e.g. ``main.py``
    lifespan startup) to avoid racing with a background auto-start task that
    would otherwise stop+restart the stream concurrently.
    """
    def __enter__(self):
        global _suppress_autostart
        self._prev = _suppress_autostart
        _suppress_autostart = True
        return self

    def __exit__(self, exc_type, exc, tb):
        global _suppress_autostart
        _suppress_autostart = self._prev
        return False


def suppress_autostart() -> _AutostartGuard:
    """Suppress registry auto-start inside the returned ``with`` block."""
    return _AutostartGuard()


def get_provider() -> MarketDataProvider:
    """Get the configured market data provider (singleton).

    Provider selection is gated by api_type:
      - "indian"  -> fyers
      - "crypto"  -> binance

    The active provider comes from app.core.broker_runtime, which honors the
    saved user settings (app_settings.broker.provider) and falls back to the
    MARKET_DATA_PROVIDER env var. Credentials saved in the settings UI are
    injected into the provider so live data fetching activates (instead of
    always falling back to the DEMO provider).

    On first lazy creation (or after reset_provider), the provider's
    start_stream() is auto-scheduled so the licensed feed begins ingesting
    ticks into central_feed immediately. Without this, settings-save would
    rebuild the provider but never start its stream, leaving MARKET_TICKS=0.
    """
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = _create_provider()
        _schedule_start_stream(_provider_instance)
    return _provider_instance


def reset_provider() -> None:
    """Drop the cached provider (used by tests / settings reload).

    Keeps a reference to the previous provider so the caller (settings save /
    token refresh) can stop its stream and restart the new provider's stream
    cleanly — otherwise the old stream keeps producing ticks for a discarded
    instance while the new singleton never starts.
    """
    global _provider_instance, _previous_provider
    if _provider_instance is not None:
        _previous_provider = _provider_instance
        _provider_instance = None


async def stop_previous_provider_stream() -> None:
    """Stop the stream of the provider that was active before the last reset."""
    global _previous_provider
    prev = _previous_provider
    if prev is None:
        return
    try:
        await prev.stop_stream()
    except Exception as e:
        logger.debug("registry_stop_previous_stream_failed", provider=prev.provider_name, error=str(e)[:200])
    finally:
        _previous_provider = None


def get_active_provider_name() -> str:
    """Return the name of the active market data provider."""
    return get_provider().provider_name


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
    if provider_name == "flattrade":
        logger.info("provider_init", api_type=api_type, provider="flattrade", live=bool(creds))
        return FlattradeProvider(
            user_id=creds.get("user_id"),
            api_key=creds.get("api_key"),
            api_secret=creds.get("api_secret"),
            token=creds.get("token") or creds.get("access_token"),
        )
    if provider_name == "binance":
        logger.info("provider_init", api_type=api_type, provider="binance", live=bool(creds))
        return BinanceProvider(
            api_key=creds.get("api_key"),
            api_secret=creds.get("api_secret"),
        )

    raise ValueError(f"Unknown market data provider: {provider_name}")
