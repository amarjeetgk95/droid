"""Auth posture — the dev bypass must not survive off-machine or in production.

Background: `AUTH_REQUIRED` defaults to false and the old `get_current_user`
handed out `AuthUser(..., role="admin")` to *any* request without a valid token.
The backend binds to 127.0.0.1, which looks safe, but `start-mobile-tunnel.ps1`
publishes the same port to the public internet through a Cloudflare quick tunnel
(`cloudflared tunnel --url http://127.0.0.1:8000`). cloudflared connects from
loopback, so the peer address cannot tell the two apart — meaning the entire API
was reachable, unauthenticated, as an admin, by anyone with the tunnel URL.

These tests pin the fix from both sides: anonymous tunnelled traffic is refused,
and a *signed-in* operator over the tunnel still works (that is the whole point
of the mobile workflow, so it must not regress).
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from jose import jwt
from starlette.requests import Request
from starlette.testclient import TestClient

from app.core.config import settings
from app.core.security import (
    AuthUser,
    _dev_bypass_allowed,
    _request_came_through_proxy,
    _request_is_loopback,
    decode_supabase_jwt,
    require_auth,
)
from app.main import CORS_ORIGIN_REGEX, CORS_ORIGINS

DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
REAL_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_SECRET = "test-secret-not-used-outside-the-suite"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _probe_app() -> FastAPI:
    """A minimal app exposing the real dependency.

    Deliberately not a real route: this measures the guard itself rather than
    some endpoint's business logic (which would drag in the market feed, the
    database, and the signal stack).
    """
    probe = FastAPI()

    @probe.get("/whoami")
    async def whoami(user: AuthUser = Depends(require_auth)):
        return {"user_id": user.user_id, "role": user.role, "email": user.email}

    return probe


def _request(host: str | None = None, **headers: str) -> Request:
    """Build a bare Request so header parsing can be unit-tested."""
    raw: list[tuple[bytes, bytes]] = []
    if host is not None:
        raw.append((b"host", host.encode()))
    for key, value in headers.items():
        raw.append((key.replace("_", "-").encode(), value.encode()))
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": raw,
            "query_string": b"",
            "scheme": "http",
            "server": ("127.0.0.1", 8000),
            "client": ("127.0.0.1", 12345),
        }
    )


def _signed_token(sub: str = REAL_USER_ID, email: str = "operator@droid.test") -> str:
    return jwt.encode(
        {"sub": sub, "email": email, "role": "authenticated", "aud": "authenticated"},
        TEST_SECRET,
        algorithm="HS256",
    )


@pytest.fixture
def probe():
    with TestClient(_probe_app()) as c:
        yield c


@pytest.fixture
def dev_env(monkeypatch):
    """Pin the permissive local-dev posture these tests reason about."""
    monkeypatch.setattr(settings, "auth_required", False, raising=False)
    monkeypatch.setattr(settings, "app_env", "development", raising=False)
    monkeypatch.setattr(settings, "app_mode", "development", raising=False)
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET, raising=False)


# --------------------------------------------------------------------------
# host / proxy parsing
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "host,expected",
    [
        ("localhost", True),
        ("localhost:3000", True),
        ("127.0.0.1", True),
        ("127.0.0.1:8000", True),
        ("[::1]:8000", True),
        # the tunnel case
        ("random-words-here.trycloudflare.com", False),
        # a claimable Firebase project id that the old CORS regex allowed
        ("fo-droid-evil.web.app", False),
        # a LAN address — the backend does not bind these, but be explicit
        ("192.168.1.50:8000", False),
        ("", False),
    ],
)
def test_request_is_loopback_parsing(host, expected):
    assert _request_is_loopback(_request(host=host)) is expected


def test_proxy_header_detection():
    assert _request_came_through_proxy(_request("127.0.0.1:8000")) is False
    assert _request_came_through_proxy(_request("127.0.0.1:8000", cf_ray="8a1b2c3d")) is True
    assert _request_came_through_proxy(_request("127.0.0.1:8000", x_forwarded_for="203.0.113.7")) is True


# --------------------------------------------------------------------------
# the bypass: allowed locally, refused otherwise
# --------------------------------------------------------------------------

def test_dev_bypass_grants_admin_on_loopback(dev_env, probe):
    """Local development must keep working exactly as before."""
    r = probe.get("/whoami")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == DEV_USER_ID
    assert body["role"] == "admin"


def test_dev_bypass_allowed_helper_on_loopback(dev_env):
    assert _dev_bypass_allowed(_request("127.0.0.1:8000")) is True


def test_tunnel_host_is_refused(dev_env, probe):
    """The headline fix: a tunnelled anonymous request is no longer an admin."""
    r = probe.get("/whoami", headers={"host": "random-words.trycloudflare.com"})
    assert r.status_code == 401


def test_tunnel_refused_even_when_host_looks_local(dev_env, probe):
    """Defence in depth against cloudflared rewriting `Host` to the origin.

    Cloudflare always adds these headers and a client cannot strip them, so this
    signal holds even if the Host header comes through as 127.0.0.1:8000.
    """
    r = probe.get(
        "/whoami",
        headers={
            "host": "127.0.0.1:8000",
            "cf-connecting-ip": "203.0.113.7",
            "cf-ray": "8a1b2c3d4e5f-LHR",
        },
    )
    assert r.status_code == 401


def test_forwarded_header_is_refused(dev_env, probe):
    r = probe.get("/whoami", headers={"host": "127.0.0.1:8000", "x-forwarded-for": "203.0.113.7"})
    assert r.status_code == 401


def test_dev_bypass_denied_helper_when_proxied(dev_env):
    assert _dev_bypass_allowed(_request("127.0.0.1:8000", cf_connecting_ip="203.0.113.7")) is False


def test_production_suppresses_dev_bypass(dev_env, monkeypatch, probe):
    """Production enforces auth even if AUTH_REQUIRED was left false."""
    monkeypatch.setattr(settings, "app_mode", "production", raising=False)
    r = probe.get("/whoami")
    assert r.status_code == 401


def test_staging_suppresses_dev_bypass(dev_env, monkeypatch, probe):
    """`app_env` alone is enough — the two env fields must both be honoured."""
    monkeypatch.setattr(settings, "app_env", "production", raising=False)
    r = probe.get("/whoami")
    assert r.status_code == 401


def test_auth_required_suppresses_dev_bypass(dev_env, monkeypatch, probe):
    monkeypatch.setattr(settings, "auth_required", True, raising=False)
    r = probe.get("/whoami")
    assert r.status_code == 401


# --------------------------------------------------------------------------
# tokens
# --------------------------------------------------------------------------

def test_valid_token_resolves_real_user_over_tunnel(dev_env, probe):
    """The mobile workflow must survive: a signed-in operator still works.

    Without this, tightening the guard would have broken the tunnel for its
    only legitimate use.
    """
    r = probe.get(
        "/whoami",
        headers={
            "host": "random-words.trycloudflare.com",
            "cf-connecting-ip": "203.0.113.7",
            "cf-ray": "8a1b2c3d4e5f-LHR",
            "authorization": f"Bearer {_signed_token()}",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == REAL_USER_ID
    assert body["email"] == "operator@droid.test"


def test_invalid_token_is_refused_when_proxied(dev_env, probe):
    """A bad token must never degrade into an anonymous admin off-machine."""
    r = probe.get(
        "/whoami",
        headers={
            "host": "random-words.trycloudflare.com",
            "cf-ray": "8a1b2c3d4e5f-LHR",
            "authorization": "Bearer not-a-real-jwt",
        },
    )
    assert r.status_code == 401


def test_invalid_token_still_tolerated_in_local_dev(dev_env, probe):
    """Preserved: local dev ignores an unusable token rather than 401-ing.

    This is what keeps the local frontend working when a stale Supabase token is
    sitting in localStorage.
    """
    r = probe.get("/whoami", headers={"authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 200
    assert r.json()["user_id"] == DEV_USER_ID


def test_auth_required_rejects_invalid_token(dev_env, monkeypatch, probe):
    monkeypatch.setattr(settings, "auth_required", True, raising=False)
    r = probe.get("/whoami", headers={"authorization": "Bearer not-a-real-jwt"})
    assert r.status_code == 401


# --------------------------------------------------------------------------
# CORS
#
# These run against a throwaway app carrying the same middleware configuration,
# rather than the real app, so the suite does not start the signal workers just
# to check a response header. `test_real_app_wires_the_hardened_cors_config`
# below pins that the real app actually uses these constants.
# --------------------------------------------------------------------------

def _cors_app() -> FastAPI:
    cors_app = FastAPI()
    cors_app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_origin_regex=CORS_ORIGIN_REGEX,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @cors_app.get("/")
    async def root():
        return {"ok": True}

    return cors_app


@pytest.fixture(scope="module")
def cors_client():
    with TestClient(_cors_app()) as c:
        yield c


@pytest.mark.parametrize(
    "origin,allowed",
    [
        ("https://fo-droid.web.app", True),
        ("https://fo-droid.firebaseapp.com", True),
        ("http://localhost:3000", True),
        ("http://127.0.0.1:3000", True),
        ("http://localhost:5173", True),
        # prefix wildcard that the old regex accepted — a claimable project id
        ("https://fo-droid-evil.web.app", False),
        ("https://fo-droid-attacker.firebaseapp.com", False),
        # arbitrary loopback port that the old regex accepted
        ("http://localhost:9999", False),
        ("http://127.0.0.1:12345", False),
        ("https://evil.example.com", False),
    ],
)
def test_cors_origin_allowlist(cors_client, origin, allowed):
    r = cors_client.get("/", headers={"Origin": origin})
    assert r.status_code == 200
    assert (r.headers.get("access-control-allow-origin") == origin) is allowed


def test_real_app_wires_the_hardened_cors_config():
    """Guards against the old wildcard regex being pasted back in."""
    from app.main import app as real_app

    cors = [m for m in real_app.user_middleware if getattr(m, "cls", None) is CORSMiddleware]
    assert cors, "CORSMiddleware is not installed on the real app"
    kwargs = cors[0].kwargs
    assert kwargs.get("allow_origin_regex") == CORS_ORIGIN_REGEX
    assert kwargs.get("allow_origins") == CORS_ORIGINS
    # The two holes that were closed must not reappear.
    assert r"(:\d+)?" not in CORS_ORIGIN_REGEX
    assert "fo-droid.*" not in CORS_ORIGIN_REGEX
