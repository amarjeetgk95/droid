"""Runtime broker configuration — LOCAL hardcoded-only.

Single-broker localhost deployment: FYERS app_id/secret_key come ONLY from
backend/.env (``FYERS_APP_ID`` / ``FYERS_SECRET_KEY``). Values saved via the
Settings UI are IGNORED for app_id/secret — this ends the hybrid
``AppID(saved)+Secret(env)`` mismatch that caused ``invalid app id hash``.

Only the OAuth access_token is runtime-mutable (set by /fyers/callback after
a successful exchange, held in memory). Frontend never sends secrets.
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
}

# Canonical ctor arg -> ALL accepted saved-field aliases (kept for reading
# legacy DB blobs / OAuth dual-write). NOTE: app_id/secret_key from saved
# settings are IGNORED — env is the sole source (see apply_app_settings).
_PROVIDER_CRED_ALIASES: Dict[str, Dict[str, tuple[str, ...]]] = {
    "fyers": {
        "app_id": ("appId", "app_id", "appID", "client_id", "clientId"),
        "secret_key": ("secret", "secret_key", "secretKey", "secretId", "secretID"),
        "access_token": ("access_token", "accessToken", "token", "access_token_key"),
    },
}

_PROVIDER_CRED_KEYS: Dict[str, Dict[str, str]] = {
    "fyers": {"app_id": "appId", "secret_key": "secret", "access_token": "access_token"},
}


# Tokens that are clearly not real broker credentials (test fixtures, docs
# examples, copy-paste accidents). Treated as ABSENT everywhere so health
# checks stay honest and the provider parks with "re-auth required" instead
# of hammering the broker API with a 401 on every poll cycle.
_KNOWN_DUMMY_TOKENS = frozenset({
    "",
    "mock-demo-token",
    "changeme",
    "test123",
    "valid_fyers_jwt_token_123",
})

# Substrings that never appear in real FYERS access tokens but show up in
# placeholders. Matched case-insensitively.
_PLACEHOLDER_MARKERS = (
    "mock",
    "dummy",
    "placeholder",
    "example",
    "changeme",
    "sample",
    "fake",
    "valid_",
    "test_",
    "_test",
    "testing",
)


def is_usable_access_token(token: object) -> bool:
    """True only if `token` looks like a real broker access token.

    Guards against placeholder values (e.g. ``valid_fyers_jwt_token_123``)
    that would otherwise count as "configured" in health checks while every
    live data call fails authentication.
    """
    if not isinstance(token, str):
        return False
    cleaned = token.strip().strip("\"'")
    if not cleaned or cleaned in _KNOWN_DUMMY_TOKENS:
        return False
    # Real FYERS tokens are long opaque/JWT strings; anything this short is
    # a stub, not a credential.
    if len(cleaned) < 32:
        return False
    lowered = cleaned.lower()
    return not any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


@dataclass
class BrokerConfig:
    provider: str
    api_type: str
    credentials: Dict[str, Any] = field(default_factory=dict)


_active: Optional[BrokerConfig] = None


def _env_config() -> BrokerConfig:
    """Build a config from static env-driven settings (fallback / startup)."""
    from app.core.config import settings as cfg

    provider = "fyers"

    # Populate credentials from env so provider starts LIVE without needing Settings UI save
    creds: Dict[str, Any] = {}
    if cfg.fyers_app_id:
        creds["app_id"] = cfg.fyers_app_id.strip().strip("\"'")
    if cfg.fyers_secret_key:
        creds["secret_key"] = cfg.fyers_secret_key.strip().strip("\"'")
    token = (cfg.fyers_access_token or "").strip().strip("\"'")
    if not token:
        from pathlib import Path
        token_file = Path(".fyers_token")
        if token_file.exists():
            try:
                token = token_file.read_text(encoding="utf-8").strip()
            except Exception:
                token = ""

    if token:
        if is_usable_access_token(token):
            creds["access_token"] = token
        else:
            logger.warning(
                "fyers_token_placeholder_ignored",
                hint="Stored FYERS token looks like a placeholder, not a real credential — re-auth required via /api/v1/tokens/fyers/auth-url",
            )

    return BrokerConfig(provider=provider, api_type="indian", credentials=creds)


def _creds_from_app_settings(app_settings: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ONLY the runtime access_token from saved app_settings.

    app_id/secret_key from the Settings UI are deliberately IGNORED —
    hardcoded localhost .env is the sole source. Accepting saved secrets
    caused hybrid mismatches (saved App ID + env Secret) -> Fyers
    ``invalid app id hash``. Legacy blobs are still parsed so old DB rows
    don't crash, but only the token is returned.
    """
    broker = (app_settings or {}).get("broker") or {}
    if not isinstance(broker, dict):
        broker = app_settings if isinstance(app_settings, dict) else {}
    provider = broker.get("provider") or (app_settings or {}).get("preferred_market_provider")
    saved_key = _PROVIDER_SAVED_KEY.get(provider or "")
    aliases = _PROVIDER_CRED_ALIASES.get(provider or "")
    if not saved_key or not aliases:
        return {}
    raw = broker.get(saved_key) or {}
    if not isinstance(raw, dict):
        raw = {}
    creds: Dict[str, Any] = {}
    # Hardcoded-only: ignore saved app_id/secret_key entirely.
    token_fields = aliases.get("access_token", ())
    for f in token_fields:
        val = raw.get(f)
        if val not in (None, ""):
            cleaned = val.strip().strip("\"'") if isinstance(val, str) else val
            if is_usable_access_token(cleaned):
                creds["access_token"] = cleaned
            else:
                logger.warning(
                    "broker_saved_token_placeholder_ignored",
                    hint="Saved broker token looks like a placeholder — re-auth required",
                )
            break
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
    """Refresh runtime state — hardcoded localhost .env wins.

    - app_id/secret_key: ALWAYS from env (``FYERS_APP_ID``/``FYERS_SECRET_KEY``).
      Saved Settings values are ignored (see _creds_from_app_settings).
    - access_token: env base + OAuth/saved token overlay (in-memory session).
    - provider/api_type: fyers/indian fixed for localhost single-broker.

    Returns True if the active provider changed and the caller should reset the
    provider singleton.
    """
    global _active
    if not app_settings:
        # No saved settings — revert to env-driven config.
        _active = _env_config()
        logger.info("broker_config_reverted_to_env", provider=_active.provider)
        return True

    provider = _provider_from_app_settings(app_settings)
    env_cfg = _env_config()
    if not provider:
        # Saved settings exist but no recognizable broker provider — fall back.
        _active = env_cfg
        logger.info("broker_config_no_saved_provider", provider=_active.provider)
        return True

    # Determine api_type from saved settings, else keep env default.
    broker = app_settings.get("broker") or {}
    api_type = broker.get("apiType") or env_cfg.api_type

    saved_creds = _creds_from_app_settings(app_settings)
    # Hardcoded-only: env supplies app_id/secret; saved blob may only add token.
    base_creds = dict(env_cfg.credentials) if env_cfg.provider == provider else {}
    if "app_id" in saved_creds or "secret_key" in saved_creds:
        logger.warning("broker_saved_creds_ignored", keys=list(saved_creds.keys()))
    saved_creds.pop("app_id", None)
    saved_creds.pop("secret_key", None)
    creds = {**base_creds, **saved_creds}
    source = "local_env"
    if saved_creds.get("access_token"):
        source = "local_env+token"
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
        saved_cred_count=len(saved_creds),
        env_cred_count=len(base_creds),
        source=source,
    )
    return changed


def reset() -> None:
    """Drop the cached broker config (forces re-derivation on next access)."""
    global _active
    _active = None
