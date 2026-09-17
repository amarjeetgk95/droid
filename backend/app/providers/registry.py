from app.providers.base import MarketDataProvider
from app.providers.fyers import FyersProvider
from app.core.broker_runtime import get_config
import asyncio
import structlog

logger = structlog.get_logger()

INDIAN_PROVIDERS = ("fyers",)

_provider_instance: MarketDataProvider | None = None
_previous_provider: MarketDataProvider | None = None
_stream_start_task: asyncio.Task | None = None
_suppress_autostart: bool = False
_provider_rejected: str | None = None  # last rejected provider selection, for health surfacing


def get_broker_provider_status() -> str:
    """Return the provider posture for /health/subsystems.

    "ok:fyers" when the singleton is active; "rejected:<value>" when a
    non-fyers selection was refused; "unset" when no provider exists yet.
    """
    if _provider_rejected:
        return f"rejected:{_provider_rejected}"
    if _provider_instance is not None:
        return f"ok:{getattr(_provider_instance, 'provider_name', 'unknown')}"
    return "unset"


def _schedule_start_stream(provider: MarketDataProvider) -> None:
    """DEPRECATED — backend lifecycle owns provider startup (see
    app.core.service_lifecycle.ensure_provider_stream, called from lifespan).

    Frontend REST/WS requests must NEVER start the upstream stream; they only
    consume data already managed by the backend. Kept as a no-op so existing
    imports don't break.
    """
    logger.debug(
        "registry_autostart_suppressed_by_lifecycle",
        provider=getattr(provider, "provider_name", "unknown"),
    )


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

    Provider selection defaults to fyers (Indian F&O).

    The active provider comes from app.core.broker_runtime, which honors the
    saved user settings (app_settings.broker.provider) and falls back to the
    MARKET_DATA_PROVIDER env var. Credentials saved in the settings UI are
    injected into the provider so live data fetching activates (instead of
    always falling back to the DEMO provider).

    Lifecycle: this ONLY creates/returns the singleton — it never starts the
    stream. The stream is started exactly once by backend lifespan via
    app.core.service_lifecycle.ensure_provider_stream(), and restarted only
    via service_lifecycle.restart_provider_stream() when broker config
    changes. Frontend connections merely consume central_feed data.
    """
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = _create_provider()
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

    Fyers-only policy (Truth of Wall): the saved user settings / env may only
    select ``fyers``. Any other selection is rejected LOUDLY — it never falls
    back silently to fyers while pretending the configured choice is active.
    The rejection is surfaced via /health/subsystems (broker_provider_status)
    and leaves the provider singleton unset so every data path fails closed
    to OFFLINE instead of serving data under a wrong provider identity.
    """
    global _provider_rejected
    cfg = get_config()
    creds = cfg.credentials or {}
    requested = (cfg.provider or "").strip().lower()
    if requested != "fyers":
        _provider_rejected = requested
        logger.error(
            "provider_config_rejected",
            requested=requested,
            policy="fyers-only (Truth of Wall)",
            detail="No provider instance created — market data paths will fail closed to OFFLINE.",
        )
        raise RuntimeError(
            f"Broker provider '{requested}' is not supported — this platform is FYERS-only. "
            "Fix the saved broker settings (Settings UI) or MARKET_DATA_PROVIDER env.",
        )
    _provider_rejected = None
    logger.info("provider_init", api_type="indian", provider="fyers", live=bool(creds))
    return FyersProvider(
        app_id=creds.get("app_id"),
        secret_key=creds.get("secret_key"),
        access_token=creds.get("access_token"),
    )
