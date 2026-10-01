"""Tests for FYERS historical provider auth resolution and fail-honest errors."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

from app.core.broker_runtime import current_access_token
from app.historical_data.providers.fyers import FYERSAuthError, FYERSHistoricalProvider


def _jwt(exp_epoch: int) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp_epoch}).encode()).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def _future_jwt() -> str:
    return _jwt(int((datetime.now(timezone.utc) + timedelta(hours=12)).timestamp()))


def _past_jwt() -> str:
    return _jwt(int((datetime.now(timezone.utc) - timedelta(hours=12)).timestamp()))


def test_current_access_token_prefers_unexpired_jwt(monkeypatch, tmp_path):
    """A live token file must beat an expired .env token (the 22-Sep bug)."""
    from app.core import broker_runtime

    expired_env = _past_jwt()
    live_file = _future_jwt()

    monkeypatch.setattr(broker_runtime, "_read_token_file", lambda: live_file)
    monkeypatch.setattr(broker_runtime, "_active", None)
    monkeypatch.setattr("app.core.config.settings.fyers_access_token", expired_env)

    assert current_access_token() == live_file


def test_current_access_token_returns_empty_when_nothing_usable(monkeypatch):
    from app.core import broker_runtime

    monkeypatch.setattr(broker_runtime, "_read_token_file", lambda: "")
    monkeypatch.setattr(broker_runtime, "_active", None)
    monkeypatch.setattr("app.core.config.settings.fyers_access_token", "")

    assert current_access_token() == ""


def test_provider_uses_runtime_token_not_stale_env(monkeypatch):
    """Provider must resolve the freshest token per request, not ctor-time env."""
    from app.core import broker_runtime

    live = _future_jwt()
    monkeypatch.setattr(broker_runtime, "_read_token_file", lambda: live)
    monkeypatch.setattr(broker_runtime, "_active", None)
    monkeypatch.setattr("app.core.config.settings.fyers_access_token", _past_jwt())

    provider = FYERSHistoricalProvider()
    header = provider._get_auth_header()
    assert header.endswith(live)


def test_provider_explicit_ctor_token_wins(monkeypatch):
    from app.core import broker_runtime

    explicit = _future_jwt()
    monkeypatch.setattr(broker_runtime, "_read_token_file", lambda: _past_jwt())
    monkeypatch.setattr(broker_runtime, "_active", None)

    provider = FYERSHistoricalProvider(access_token=explicit)
    assert provider._get_access_token() == explicit


@pytest.mark.asyncio
async def test_fetch_chunk_raises_auth_error_without_usable_token(monkeypatch):
    """Missing credentials must raise, not silently return [] (fake no-data)."""
    from app.core import broker_runtime

    monkeypatch.setattr(broker_runtime, "_read_token_file", lambda: "")
    monkeypatch.setattr(broker_runtime, "_active", None)
    monkeypatch.setattr("app.core.config.settings.fyers_access_token", "")

    provider = FYERSHistoricalProvider()
    with pytest.raises(FYERSAuthError):
        await provider.fetch_chunk("SENSEX", "1m", __import__("datetime").date(2026, 9, 23), __import__("datetime").date(2026, 9, 24))
