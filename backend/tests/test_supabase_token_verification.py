"""Supabase access-token verification — ES256 via JWKS, plus the legacy HS256 path.

The backend previously verified only `algorithms=["HS256"]` against
`settings.supabase_jwt_secret`. The live Supabase project publishes a single
signing key:

    GET https://<ref>.supabase.co/auth/v1/.well-known/jwks.json
    {"keys":[{"kty":"EC","alg":"ES256","crv":"P-256",...}]}

An ES256 token can never be validated with an HS256 shared secret, so **every**
real access token was rejected. That is why the dev bypass was load-bearing:
the app only worked because authentication was silently ignored.

These tests pin the asymmetric path and the attacks it must still refuse.
"""

from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from fastapi import HTTPException
from jose import jwt

from app.core.config import settings
from app.core.security import decode_supabase_jwt

REAL_USER_ID = "11111111-1111-1111-1111-111111111111"
TEST_KID = "test-kid-0001"
TEST_SECRET = "legacy-shared-secret"
JWKS_PATH = "/auth/v1/.well-known/jwks.json"


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------

def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _segment(obj: dict) -> str:
    return _b64u(json.dumps(obj, separators=(",", ":")).encode())


def _ec_keypair() -> tuple[object, dict]:
    """A P-256 keypair plus its public JWK, shaped like Supabase's."""
    priv = ec.generate_private_key(ec.SECP256R1())
    nums = priv.public_key().public_numbers()
    jwk = {
        "kty": "EC",
        "crv": "P-256",
        "alg": "ES256",
        "use": "sig",
        "kid": TEST_KID,
        "x": _b64u(nums.x.to_bytes(32, "big")),
        "y": _b64u(nums.y.to_bytes(32, "big")),
    }
    return priv, jwk


def _sign_es256(priv, claims: dict, kid: str = TEST_KID, alg: str = "ES256") -> str:
    """Sign a JWT the way Supabase does: ES256 over SHA-256, raw r||s signature."""
    header = {"alg": alg, "typ": "JWT", "kid": kid}
    signing_input = f"{_segment(header)}.{_segment(claims)}".encode()
    der = priv.sign(signing_input, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der)
    signature = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return f"{_segment(header)}.{_segment(claims)}.{_b64u(signature)}"


def _claims(**overrides) -> dict:
    base = {
        "sub": REAL_USER_ID,
        "email": "operator@droid.test",
        "role": "authenticated",
        "aud": "authenticated",
        "exp": int(time.time()) + 3600,
    }
    base.update(overrides)
    return base


@pytest.fixture
def jwks(monkeypatch):
    """Serve a generated ES256 public key as the project's JWKS."""
    import app.core.security as sec

    priv, jwk = _ec_keypair()
    doc = {"keys": [jwk]}

    async def _fake_fetch(force: bool = False):
        return doc

    monkeypatch.setattr(sec, "_fetch_jwks", _fake_fetch)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co", raising=False)
    monkeypatch.setattr(settings, "supabase_jwt_secret", "", raising=False)
    sec._jwks_cache.clear()
    return priv


# --------------------------------------------------------------------------
# the happy path
# --------------------------------------------------------------------------

async def test_es256_token_verifies_via_jwks(jwks):
    """The headline fix: a real Supabase-shaped token now decodes."""
    payload = await decode_supabase_jwt(_sign_es256(jwks, _claims()))
    assert payload["sub"] == REAL_USER_ID
    assert payload["email"] == "operator@droid.test"


async def test_legacy_hs256_still_works(monkeypatch):
    """A project on the old shared-secret scheme keeps working."""
    monkeypatch.setattr(settings, "supabase_jwt_secret", TEST_SECRET, raising=False)
    token = jwt.encode(_claims(), TEST_SECRET, algorithm="HS256")
    payload = await decode_supabase_jwt(token)
    assert payload["sub"] == REAL_USER_ID


# --------------------------------------------------------------------------
# must be refused
# --------------------------------------------------------------------------

async def test_es256_token_signed_by_another_key_is_rejected(jwks):
    other_priv, _ = _ec_keypair()
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_sign_es256(other_priv, _claims()))
    assert exc.value.status_code == 401


async def test_expired_es256_token_is_rejected(jwks):
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_sign_es256(jwks, _claims(exp=int(time.time()) - 60)))
    assert exc.value.status_code == 401


async def test_wrong_audience_is_rejected(jwks):
    """A service_role token must not authenticate as a user."""
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_sign_es256(jwks, _claims(aud="service_role")))
    assert exc.value.status_code == 401


async def test_alg_none_is_rejected(jwks):
    """Classic alg-confusion: an unsigned token must never be accepted."""
    unsigned = f"{_segment({'alg': 'none', 'typ': 'JWT'})}.{_segment(_claims())}."
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(unsigned)
    assert exc.value.status_code == 401


async def test_unsupported_alg_is_rejected(jwks):
    """`alg` is never taken from the token — only from a strict allowlist."""
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_sign_es256(jwks, _claims(), alg="HS512"))
    assert exc.value.status_code == 401


async def test_garbage_token_is_401_not_503(jwks):
    """A malformed credential is a client error, not a config error."""
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt("not-a-jwt-at-all")
    assert exc.value.status_code == 401


async def test_hs256_without_secret_is_503(monkeypatch):
    monkeypatch.setattr(settings, "supabase_jwt_secret", "", raising=False)
    token = jwt.encode(_claims(), TEST_SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(token)
    assert exc.value.status_code == 503


# --------------------------------------------------------------------------
# JWKS fetching, key rotation and failure modes
# --------------------------------------------------------------------------

async def test_unknown_kid_refreshes_once_then_rejects(monkeypatch):
    """A rotated key triggers one refresh; a still-unknown kid is a 401."""
    import app.core.security as sec

    priv, jwk = _ec_keypair()
    calls: list[bool] = []

    async def _fake_fetch(force: bool = False):
        calls.append(force)
        return {"keys": [jwk]}          # never contains the kid we sign with

    monkeypatch.setattr(sec, "_fetch_jwks", _fake_fetch)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co", raising=False)
    sec._jwks_cache.clear()

    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_sign_es256(priv, _claims(), kid="some-other-kid"))
    assert exc.value.status_code == 401
    assert calls == [False, True], "should have forced exactly one refresh"


def test_jwks_url_construction(monkeypatch):
    import app.core.security as sec

    monkeypatch.setattr(settings, "supabase_url", "", raising=False)
    assert sec._jwks_url() == ""
    monkeypatch.setattr(settings, "supabase_url", "https://x.supabase.co/", raising=False)
    assert sec._jwks_url() == f"https://x.supabase.co{JWKS_PATH}"


async def test_jwks_is_fetched_over_http_and_then_cached(monkeypatch):
    """Exercises the real fetch path (URL, parsing, caching) without a network."""
    import app.core.security as sec

    priv, jwk = _ec_keypair()
    doc = {"keys": [jwk]}
    hits: list[str] = []

    class _Resp:
        def raise_for_status(self):
            pass

        def json(self):
            return doc

    class _Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            hits.append(url)
            return _Resp()

    monkeypatch.setattr(sec.httpx, "AsyncClient", _Client)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co", raising=False)
    monkeypatch.setattr(settings, "supabase_jwt_secret", "", raising=False)
    sec._jwks_cache.clear()

    token = _sign_es256(priv, _claims())
    assert (await decode_supabase_jwt(token))["sub"] == REAL_USER_ID
    assert (await decode_supabase_jwt(token))["sub"] == REAL_USER_ID

    assert hits == [f"https://example.supabase.co{JWKS_PATH}"], \
        "JWKS should be fetched once and then served from cache"


async def test_jwks_fetch_failure_is_503(monkeypatch):
    """An unreachable identity provider must not look like a bad token."""
    import app.core.security as sec

    priv, _ = _ec_keypair()

    class _Boom:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            raise RuntimeError("network down")

    monkeypatch.setattr(sec.httpx, "AsyncClient", _Boom)
    monkeypatch.setattr(settings, "supabase_url", "https://example.supabase.co", raising=False)
    sec._jwks_cache.clear()

    with pytest.raises(HTTPException) as exc:
        await decode_supabase_jwt(_sign_es256(priv, _claims()))
    assert exc.value.status_code == 503
