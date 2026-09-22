"""Unit/integration tests for the shared API helpers in ``app/api/dependencies.py``.

These pin the exact semantics the routers relied on before the extraction:

* ``AuthUser`` -> UUID parsing (missing / empty / malformed id -> None),
* ``require_user_uuid`` raising the canonical 401,
* account resolution delegating to ``AlgoAccountService`` (default capital
  config created, deterministic synthetic fallback when the DB is
  unavailable),
* representative routes still emitting the unchanged ``{data, error, meta}``
  envelope.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.algo.algo_service import algo_account_service
from app.algo.models import AlgoAccount, AlgoCapitalConfig
from app.api.dependencies import (
    get_capital_config,
    get_or_create_account,
    parse_user_uuid,
    require_user_uuid,
)
from app.core.security import AuthUser
from app.main import app

FIXED_UID = UUID("00000000-0000-0000-0000-0000000000AA")


class TestParseUserUuid:
    def test_none_user_returns_none(self):
        assert parse_user_uuid(None) is None

    def test_empty_user_id_returns_none(self):
        assert parse_user_uuid(AuthUser(user_id="")) is None

    def test_valid_user_id_is_parsed(self):
        assert parse_user_uuid(AuthUser(user_id=str(FIXED_UID))) == FIXED_UID

    def test_malformed_user_id_returns_none(self):
        assert parse_user_uuid(AuthUser(user_id="not-a-uuid")) is None


class TestRequireUserUuid:
    def test_valid_user_returns_uuid(self):
        assert require_user_uuid(AuthUser(user_id=str(FIXED_UID))) == FIXED_UID

    def test_missing_user_raises_canonical_401(self):
        with pytest.raises(HTTPException) as exc:
            require_user_uuid(None)
        assert exc.value.status_code == 401
        assert exc.value.detail == "Authentication required"

    def test_malformed_user_raises_canonical_401(self):
        with pytest.raises(HTTPException) as exc:
            require_user_uuid(AuthUser(user_id="not-a-uuid"))
        assert exc.value.status_code == 401
        assert exc.value.detail == "Authentication required"


class TestGetOrCreateAccount:
    async def test_synthetic_fallback_when_db_unavailable(self, monkeypatch):
        monkeypatch.setattr("app.algo.algo_service.settings.database_url", "")
        algo_account_service.reset()

        acct = await get_or_create_account(None, FIXED_UID)

        assert acct.id == FIXED_UID
        assert acct.user_id == FIXED_UID
        assert acct.mode == "OFF"
        assert acct.is_active is True
        # Deterministic: the cached synthetic account is returned on repeat calls.
        assert await get_or_create_account(None, FIXED_UID) is acct

    async def test_delegates_to_algo_account_service(self):
        session = AsyncMock()
        sentinel = object()
        with patch.object(
            algo_account_service,
            "get_or_create_account",
            AsyncMock(return_value=sentinel),
        ) as mocked:
            result = await get_or_create_account(session, FIXED_UID)
        assert result is sentinel
        mocked.assert_awaited_once_with(session, FIXED_UID)

    async def test_creation_creates_default_capital(self, monkeypatch):
        monkeypatch.setattr(
            "app.algo.algo_service.settings.database_url",
            "postgresql+asyncpg://user:pw@localhost/db",
        )
        algo_account_service.reset()

        profile_result = MagicMock()
        profile_result.scalar_one_or_none.return_value = None
        account_result = MagicMock()
        account_result.scalar_one_or_none.return_value = None

        session = AsyncMock()
        session.execute.side_effect = [profile_result, account_result]
        added: list = []
        # SQLAlchemy's ``session.add`` is synchronous; keep it a plain mock so
        # the service's call actually records the attached rows.
        session.add = MagicMock(side_effect=added.append)

        acct = await get_or_create_account(session, FIXED_UID)

        assert isinstance(acct, AlgoAccount)
        assert acct.user_id == FIXED_UID
        assert any(isinstance(obj, AlgoAccount) for obj in added)
        cfg = next(obj for obj in added if isinstance(obj, AlgoCapitalConfig))
        assert cfg.account_id == acct.id
        session.commit.assert_awaited()


class TestGetCapitalConfig:
    async def test_returns_row_when_present(self):
        session = AsyncMock()
        result = MagicMock()
        row = object()
        result.scalar_one_or_none.return_value = row
        session.execute.return_value = result

        assert await get_capital_config(session, FIXED_UID) is row
        session.execute.assert_awaited_once()

    async def test_returns_none_when_absent(self):
        session = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        session.execute.return_value = result

        assert await get_capital_config(session, FIXED_UID) is None


def test_algo_account_route_response_shape():
    """GET /algo/account keeps its exact envelope: no keys added or removed."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/algo/account")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"data", "error", "meta"}
    assert body["error"] is None
    assert set(body["meta"].keys()) == {"provider", "timestamp", "status"}
    assert body["meta"]["provider"] == "algo_engine"
    assert set(body["data"].keys()) == {
        "account_id",
        "user_id",
        "mode",
        "is_active",
        "capital",
        "consent_ok",
        "disclosure_version",
    }


def test_paper_portfolio_route_response_shape():
    """GET /paper/portfolio keeps its exact envelope after the parser extraction."""
    with TestClient(app) as client:
        resp = client.get("/api/v1/paper/portfolio")

    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"data", "error", "meta"}
    assert body["error"] is None
    assert set(body["meta"].keys()) == {"provider", "timestamp", "status"}
    assert body["meta"]["provider"] == "paper_trading_engine"
    assert "virtual_capital" in body["data"]
