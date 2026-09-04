"""Runtime broker configuration.

The market-data provider is a process-wide singleton (see
``app.providers.registry``). Historically it was chosen exclusively from the
``MARKET_DATA_PROVIDER`` env var at startup, which meant credentials saved via
the settings UI (``app_settings.broker.*``) had no effect and the backend kept
serving DEMO data.

This module introduces a cached, runtime-reloadable broker configuration that
is populated from the persisted user settings (``app_settings``) and falls back
to env/config when no saved settings exist. The settings endpoints call
:func:`apply_app_settings` after persisting, which refreshes the cache and
resets the provider singleton so changes take effect immediately (without a
backend restart).

Env (``MARKET_DATA_PROVIDER`` / ``API_TYPE`` + ``FYERS_*`` etc.)
remains the source of truth when no user settings are saved, which keeps
the single-broker-per-deployment model and Render env-driven config working
out of the box.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()

# Maps provider id -> the saved credential key under app_settings.broker AND the
# mapping of provider-constructor arg -> saved field name.
_PROVIDER_SAVED_KEY: Dict[str, str] = {
    "fyers": "fyers",
    "flattrade": "flattrade",
    "binance": "binance",
}

_PROVIDER_CRED_KEYS: Dict[str, Dict[str, str]] = {
    "fyers": {"app_id": "appId", "secret_key": "secret", "access_token": "access_token"},
    "flattrade": {"user_id": "userId", "api_key": "apiKey", "api_secret": "apiSecret", "token": "token"},
    "binance": {"api_key": "apiKey", "api_secret": "apiSecret"},
}


@dataclass
class BrokerConfig:
    provider: str
    api_type: str
    credentials: Dict[str, Any] = field(default_factory=dict)


_active: Optional[BrokerConfig] = None


def _env_config() -> BrokerConfig:
    """Build a config from static env-driven settings (fallback / startup)."""
    from app.core.config import settings as cfg

    provider = cfg.market_data_provider
    if cfg.api_type == "crypto" and provider != "binance":
        provider = "binance"
    elif cfg.api_type != "crypto" and provider not in _PROVIDER_CRED_KEYS:
        provider = "fyers"

    # Populate credentials from env so provider starts LIVE without needing Settings UI save
    creds: Dict[str, Any] = {}
    if provider == "fyers":
        if cfg.fyers_app_id:
            creds["app_id"] = cfg.fyers_app_id.strip().strip("\"'")
        if cfg.fyers_secret_key:
            creds["secret_key"] = cfg.fyers_secret_key.strip().strip("\"'")
        if cfg.fyers_access_token:
            creds["access_token"] = cfg.fyers_access_token.strip().strip("\"'")
    elif provider == "flattrade":
        if cfg.flattrade_user_id:
            creds["user_id"] = cfg.flattrade_user_id.strip().strip("\"'")
        if cfg.flattrade_api_key:
            creds["api_key"] = cfg.flattrade_api_key.strip().strip("\"'")
        if cfg.flattrade_api_secret:
            creds["api_secret"] = cfg.flattrade_api_secret.strip().strip("\"'")
        if cfg.flattrade_token:
            creds["token"] = cfg.flattrade_token.strip().strip("\"'")

    return BrokerConfig(provider=provider, api_type=cfg.api_type, credentials=creds)


def _creds_from_app_settings(app_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the active provider's credentials from the saved app_settings blob."""
    broker = (app_settings or {}).get("broker") or {}
    if not isinstance(broker, dict):
        broker = app_settings if isinstance(app_settings, dict) else {}
    provider = broker.get("provider") or (app_settings or {}).get("preferred_market_provider")
    saved_key = _PROVIDER_SAVED_KEY.get(provider or "")
    key_map = _PROVIDER_CRED_KEYS.get(provider or "")
    if not saved_key or not key_map:
        return {}
    raw = broker.get(saved_key) or {}
    if not isinstance(raw, dict):
        raw = {}
    creds: Dict[str, Any] = {}
    for ctor_arg, saved_field in key_map.items():
        # Check both camelCase and snake_case variations
        val = raw.get(saved_field)
        if val in (None, ""):
            val = raw.get(ctor_arg)
        if val in (None, "") and ctor_arg == "access_token":
            val = raw.get("accessToken") or raw.get("access_token") or raw.get("token")
        if val not in (None, ""):
            creds[ctor_arg] = val.strip().strip("\"'") if isinstance(val, str) else val
    return creds


def _provider_from_app_settings(app_settings: Dict[str, Any]) -> Optional[str]:
    broker = (app_settings or {}).get("broker") or {}
    if isinstance(broker, dict):
        provider = broker.get("provider")
        if provider in _PROVIDER_CRED_KEYS:
            return provider
    # Also check if top-level has preferred_market_provider or provider
    top_provider = (app_settings or {}).get("preferred_market_provider") or (app_settings or {}).get("provider")
    if top_provider in _PROVIDER_CRED_KEYS:
        return top_provider
    return None


def get_config() -> BrokerConfig:
    """Return the active broker config, lazily initializing from env if needed."""
    global _active
    if _active is None:
        _active = _env_config()
        logger.info("broker_config_initialized", provider=_active.provider, api_type=_active.api_type, source="env")
    return _active


def apply_app_settings(app_settings: Optional[Dict[str, Any]]) -> bool:
    """Refresh the active broker config from persisted app_settings.

    Returns True if the active provider changed and the caller should reset the
    provider singleton. Credentials from saved settings take precedence over env
    so that saving broker keys in the UI actually drives live data fetching.
    """
    global _active
    if not app_settings:
        # No saved settings — revert to env-driven config.
        _active = _env_config()
        logger.info("broker_config_reverted_to_env", provider=_active.provider)
        return True

    provider = _provider_from_app_settings(app_settings)
    if not provider:
        # Saved settings exist but no recognizable broker provider — fall back.
        _active = _env_config()
        logger.info("broker_config_no_saved_provider", provider=_active.provider)
        return True

    # Determine api_type from saved settings, else keep current/env default.
    broker = app_settings.get("broker") or {}
    api_type = broker.get("apiType") or _env_config().api_type

    creds = _creds_from_app_settings(app_settings)
    new_cfg = BrokerConfig(provider=provider, api_type=api_type, credentials=creds)

    changed = _active is None or (
        _active.provider != new_cfg.provider
        or _active.api_type != new_cfg.api_type
        or _active.credentials != new_cfg.credentials
    )
    _active = new_cfg
    logger.info(
        "broker_config_updated",
        provider=provider,
        api_type=api_type,
        cred_count=len(creds),
        source="app_settings",
    )
    return changed


def reset() -> None:
    """Drop the cached broker config (forces re-derivation on next access)."""
    global _active
    _active = None
