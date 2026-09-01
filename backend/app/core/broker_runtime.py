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

Env (``MARKET_DATA_PROVIDER`` / ``API_TYPE`` + ``KOTAK_NEO_*`` / ``GROWW_*`` /
``FYERS_*`` etc.) remains the source of truth when no user settings are saved,
which keeps the single-broker-per-deployment model and Render env-driven config
working out of the box.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

import structlog

logger = structlog.get_logger()

# Maps provider id -> the saved credential key under app_settings.broker AND the
# mapping of provider-constructor arg -> saved field name. The frontend stores
# credentials under camelCase/normalized keys, while the `provider` selector is
# snake_case (e.g. provider "kotak_neo" but creds under "kotakNeo").
_PROVIDER_SAVED_KEY: Dict[str, str] = {
    "fyers": "fyers",
    "upstox": "upstox",
    "groww": "groww",
    "kotak_neo": "kotakNeo",
    "binance": "binance",
}

_PROVIDER_CRED_KEYS: Dict[str, Dict[str, str]] = {
    "fyers": {"app_id": "appId", "secret_key": "secret", "access_token": "access_token"},
    "upstox": {"api_key": "apiKey", "secret_key": "secret", "access_token": "access_token"},
    "groww": {"api_key": "apiKey", "api_secret": "apiSecret", "access_token": "access_token", "auth_mode": "authMode"},
    "kotak_neo": {
        "api_key": "apiKey",
        "api_secret": "apiSecret",
        "access_token": "access_token",
        "mobile_number": "mobileNumber",
        "mpin": "mpin",
        "totp": "totp",
    },
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
    import os

    provider = cfg.market_data_provider
    if cfg.api_type == "crypto" and provider != "binance":
        provider = "binance"
    elif cfg.api_type != "crypto" and provider not in _PROVIDER_CRED_KEYS:
        provider = "fyers"

    # Auto-select Groww when Groww creds are present but provider is still default fyers
    # You said you added valid Groww token but saw fyers DEMO 57348 — this was the root cause:
    # MARKET_DATA_PROVIDER default is fyers, so even with GROWW_API_KEY set it stayed fyers.
    # Now if Groww creds exist and Fyers creds don't, automatically use Groww (unless MARKET_DATA_PROVIDER explicitly set).
    if cfg.api_type != "crypto":
        has_groww = bool(cfg.groww_api_key or cfg.groww_api_secret or cfg.groww_access_token)
        has_fyers = bool(cfg.fyers_app_id or cfg.fyers_secret_key or cfg.fyers_access_token)
        if has_groww and not has_fyers and provider == "fyers" and not os.getenv("MARKET_DATA_PROVIDER"):
            provider = "groww"
            logger.info("broker_auto_select_groww", reason="groww creds present, fyers empty, MARKET_DATA_PROVIDER not set — switching to groww per your token")

        # Also if provider env was explicitly groww, honor it; if groww creds injected via Render env but provider not updated, switch
        if has_groww and provider != "groww" and provider in ("fyers", "upstox", "kotak_neo"):
            # If groww token is present in env, prefer groww over fyers default
            # Only auto-switch if fyers has no valid token (avoids breaking fyers users who also set groww)
            if not has_fyers:
                provider = "groww"

    # Populate credentials from env so provider starts LIVE without needing Settings UI save
    creds: Dict[str, Any] = {}
    if provider == "groww":
        if cfg.groww_api_key:
            creds["api_key"] = cfg.groww_api_key
        if cfg.groww_api_secret:
            creds["api_secret"] = cfg.groww_api_secret
        if cfg.groww_access_token:
            creds["access_token"] = cfg.groww_access_token
        if cfg.groww_auth_mode:
            creds["auth_mode"] = cfg.groww_auth_mode
    elif provider == "fyers":
        if cfg.fyers_app_id:
            creds["app_id"] = cfg.fyers_app_id
        if cfg.fyers_secret_key:
            creds["secret_key"] = cfg.fyers_secret_key
        if cfg.fyers_access_token:
            creds["access_token"] = cfg.fyers_access_token

    return BrokerConfig(provider=provider, api_type=cfg.api_type, credentials=creds)


def _creds_from_app_settings(app_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Extract the active provider's credentials from the saved app_settings blob."""
    broker = (app_settings or {}).get("broker") or {}
    if not isinstance(broker, dict):
        return {}
    provider = broker.get("provider")
    saved_key = _PROVIDER_SAVED_KEY.get(provider or "")
    key_map = _PROVIDER_CRED_KEYS.get(provider or "")
    if not saved_key or not key_map:
        return {}
    raw = broker.get(saved_key) or {}
    creds: Dict[str, Any] = {}
    for ctor_arg, saved_field in key_map.items():
        val = raw.get(saved_field)
        if val not in (None, ""):
            creds[ctor_arg] = val
    if provider == "groww":
        mode = broker.get("groww_auth_mode") or raw.get("authMode")
        if mode in ("checksum", "totp"):
            creds["auth_mode"] = mode
    return creds


def _provider_from_app_settings(app_settings: Dict[str, Any]) -> Optional[str]:
    broker = (app_settings or {}).get("broker") or {}
    if not isinstance(broker, dict):
        return None
    provider = broker.get("provider")
    if provider not in _PROVIDER_CRED_KEYS:
        return None
    return provider


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
