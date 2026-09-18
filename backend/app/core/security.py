import asyncio
import base64
import json
import time
from uuid import UUID

import httpx
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from jose.jwk import construct as jwk_construct
from app.core.config import settings
import structlog

logger = structlog.get_logger()
security_scheme = HTTPBearer(auto_error=False)

#: Reserved identity that owns the anonymous signal paper book in the DB.
#: Deliberately NOT the dev identity (`...0001`): the dev user's per-user shard
#: must stay separate from the system-owned signal book. Paper rows are
#: FK-bound to auth.users/profiles, so persistence is best-effort and degrades
#: to memory-only (with an actionable warning) until this identity is
#: provisioned in the database.
SIGNAL_BOOK_USER_ID: UUID = UUID("00000000-0000-0000-0000-0000000000A1")
SIGNAL_BOOK_LABEL = "signal-book@system.local"

#: How long a fetched JWKS is trusted before it is re-fetched.
_JWKS_TTL_SECONDS = 600

#: jwks_url -> (fetched_at, jwks_document)
_jwks_cache: dict[str, tuple[float, dict]] = {}
_jwks_lock = asyncio.Lock()

#: Host headers that mean "this request came from this machine".
#: `testserver` is Starlette/httpx `TestClient`'s default base_url host. It is
#: only safe to honour because proxied requests are independently refused below
#: — otherwise `Host: testserver` would be a trivial way to claim the bypass.
_LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})

#: Headers injected by an upstream proxy/CDN. Cloudflare adds the `cf-*` pair on
#: every tunnel request and a client cannot forge or strip them, so their
#: presence is proof the request traversed the network even though it landed on
#: loopback. This is the signal that does not depend on how cloudflared chooses
#: to rewrite `Host`.
_PROXY_HEADERS = (
    "cf-connecting-ip",
    "cf-ray",
    "cf-worker",
    "x-forwarded-for",
    "x-real-ip",
    "forwarded",
)


def _request_came_through_proxy(request: Request) -> bool:
    """True when a proxy/CDN forwarded this request to us."""
    return any(request.headers.get(h) for h in _PROXY_HEADERS)


def _request_is_loopback(request: Request) -> bool:
    """True when the request's Host header is a loopback address.

    The backend binds to 127.0.0.1, but that is **not** the same as "only
    reachable locally": `start-mobile-tunnel.ps1` puts the whole API on the
    public internet via a Cloudflare quick tunnel (`cloudflared tunnel --url
    http://127.0.0.1:8000`). cloudflared connects from loopback, so
    `request.client.host` still reads 127.0.0.1 and cannot distinguish the two
    cases. The `Host` header can: over the tunnel it is the
    `*.trycloudflare.com` name, and locally it is `localhost`/`127.0.0.1`.
    """
    host = (request.headers.get("host") or "").strip().lower()
    if host.startswith("["):          # IPv6, e.g. "[::1]:8000"
        host = host[1:].split("]", 1)[0]
    else:                             # IPv4 or name, e.g. "127.0.0.1:8000"
        host = host.rsplit(":", 1)[0]
    return host in _LOOPBACK_HOSTS


def _is_production() -> bool:
    """True when either environment field says production.

    The project carries two overlapping fields — `app_env`
    (development|staging|production) and `app_mode` (development|production) —
    both defaulting to development, and different modules read different ones.
    Checking both means a deployment that sets only one of them still fails
    closed instead of silently serving anonymous admin traffic.
    """
    return "production" in {settings.app_env, settings.app_mode}


def _dev_bypass_allowed(request: Request) -> bool:
    """Whether the unauthenticated dev identity may be handed out.

    Deliberately narrow, and deliberately redundant: the bypass is refused when
    auth is required, when the app is running as production, when any proxy
    header is present, and when the Host is not loopback. Two independent
    transport signals are used because either one alone can be defeated by an
    unexpected cloudflared configuration — together they cannot both be.
    """
    if settings.auth_required or _is_production():
        return False
    if _request_came_through_proxy(request):
        logger.warning(
            "dev_auth_bypass_denied_proxied",
            host=request.headers.get("host"),
            path=request.url.path,
            hint="request carried proxy/CDN headers; refusing dev identity",
        )
        return False
    if not _request_is_loopback(request):
        logger.warning(
            "dev_auth_bypass_denied_non_loopback",
            host=request.headers.get("host"),
            path=request.url.path,
            hint="request reached the API from a non-loopback Host; refusing dev identity",
        )
        return False
    return True


class AuthUser:
    def __init__(self, user_id: str, email: str | None = None, role: str = "user"):
        self.user_id = user_id
        self.email = email
        self.role = role

def _token_header(token: str) -> dict:
    """Read a JWT's header without verifying it.

    Only used to pick the verification strategy (`alg` / `kid`). Nothing from
    the header is trusted for authorisation — the signature is always checked
    against the algorithm we choose, never the one the token asks for.
    """
    try:
        segment = token.split(".")[0]
        segment += "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(segment))
    except Exception:
        return {}


def _jwks_url() -> str:
    base = (settings.supabase_url or "").strip().rstrip("/")
    return f"{base}/auth/v1/.well-known/jwks.json" if base else ""


async def _fetch_jwks(force: bool = False) -> dict:
    """Fetch and cache the project's JWKS.

    Supabase signs with a rotating EC P-256 key, so the key set is cached rather
    than fetched per request, and re-fetched on an unknown `kid` (rotation).
    """
    url = _jwks_url()
    if not url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not configured (SUPABASE_URL missing)",
        )

    cached = _jwks_cache.get(url)
    if cached and not force and (time.time() - cached[0]) < _JWKS_TTL_SECONDS:
        return cached[1]

    async with _jwks_lock:
        cached = _jwks_cache.get(url)
        if cached and not force and (time.time() - cached[0]) < _JWKS_TTL_SECONDS:
            return cached[1]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("jwks_fetch_failed", url=url, error=str(e)[:200])
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Unable to verify token: identity provider unreachable",
            )
        _jwks_cache[url] = (time.time(), data)
        return data


def _select_jwk(jwks: dict, kid: str | None) -> dict | None:
    keys = (jwks or {}).get("keys") or []
    if not keys:
        return None
    if kid is None:
        return keys[0]
    for key in keys:
        if key.get("kid") == kid:
            return key
    return None


async def decode_supabase_jwt(token: str) -> dict:
    """Decode and validate a Supabase access token.

    Two families are supported:

    * **Asymmetric** (`ES256` and friends) — what current Supabase projects
      issue. Verified against the project's JWKS, selected by `kid`.
    * **Shared secret** (`HS256`) — the legacy scheme. Kept so an older project
      (or a manually minted token) still works.

    The previous implementation hardcoded `algorithms=["HS256"]` against
    `supabase_jwt_secret`. For a project whose JWKS publishes an EC P-256 key
    that can never succeed — every real access token was rejected, which is why
    the dev bypass had to exist for the app to function at all.
    """
    header = _token_header(token)
    alg = (header.get("alg") or "").upper()
    kid = header.get("kid")

    if alg.startswith(("ES", "RS", "PS")):
        jwks = await _fetch_jwks()
        jwk = _select_jwk(jwks, kid)
        if jwk is None:
            # Unknown key id — most likely a rotation. Refresh once.
            jwks = await _fetch_jwks(force=True)
            jwk = _select_jwk(jwks, kid)
        if jwk is None:
            logger.warning("jwt_unknown_kid", kid=kid)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        key = jwk_construct(jwk)
        algorithms = [alg]
    elif alg in ("", "HS256"):
        if alg == "":
            # Not a decodable JWT at all — a client error, not a config error.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        if not settings.supabase_jwt_secret:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication not configured",
            )
        key = settings.supabase_jwt_secret
        algorithms = ["HS256"]
    else:
        logger.warning("jwt_unsupported_alg", alg=alg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    try:
        return jwt.decode(token, key, algorithms=algorithms, audience="authenticated")
    except JWTError as e:
        logger.warning("jwt_decode_failed", alg=alg, error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)
) -> AuthUser:
    """Resolve the calling user, failing closed.

    Contract: this either returns a real `AuthUser` or raises 401/503. It never
    returns `None`, so a route can no longer be reached anonymously by accident.

    Order of resolution:
      1. A supplied token that decodes -> that user. (Works over the tunnel too,
         so the mobile workflow keeps working for a signed-in operator.)
      2. Otherwise, the dev identity -- but only on loopback, only when auth is
         not required, and never in production.
      3. Otherwise 401.
    """
    token = credentials.credentials if credentials is not None else None

    if token:
        try:
            payload = await decode_supabase_jwt(token)
        except HTTPException:
            # A token was supplied and rejected. That must never quietly become
            # an anonymous admin. Outside permissive local dev it propagates.
            if settings.auth_required or _is_production():
                raise
            logger.debug(
                "dev_auth_token_ignored",
                host=request.headers.get("host"),
                path=request.url.path,
            )
        else:
            return AuthUser(
                user_id=payload.get("sub", ""),
                email=payload.get("email"),
                role=payload.get("role", "user"),
            )

    if _dev_bypass_allowed(request):
        # Deterministic UUID so dev DB queries resolve to a stable owner row.
        return AuthUser(
            user_id="00000000-0000-0000-0000-000000000001",
            email="dev@localhost",
            role="admin",
        )

    if token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
    )

async def require_auth(
    user: AuthUser = Depends(get_current_user)
) -> AuthUser:
    """Dependency that requires authentication.

    `get_current_user` now fails closed on its own, so this is a thin alias kept
    for readability at call sites (and so existing imports keep working). The
    previous `user is None` branch was unreachable once the dev bypass was
    gated on loopback.
    """
    return user
