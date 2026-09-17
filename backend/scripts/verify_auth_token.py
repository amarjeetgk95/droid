"""Pre-flight check: can this backend actually verify a real Supabase token?

Run this BEFORE setting AUTH_REQUIRED=true. Enabling auth when token
verification is broken locks you out of the entire application, so the point of
this script is to prove the path works with a token your browser really holds.

Get a token from the running frontend (browser devtools, on the app origin):

    copy(JSON.parse(localStorage.getItem('sb-<project-ref>-auth-token')).access_token)

Then:

    .venv/Scripts/python.exe scripts/verify_auth_token.py <token>

or pipe it in:

    echo <token> | .venv/Scripts/python.exe scripts/verify_auth_token.py -

Exit code 0 means the token verified and the API would accept it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings          # noqa: E402
from app.core.security import (               # noqa: E402
    _jwks_url,
    _fetch_jwks,
    _select_jwk,
    _token_header,
    decode_supabase_jwt,
)

OK = "[OK]"
BAD = "[FAIL]"


def _read_token(argv: list[str]) -> str:
    if len(argv) > 1 and argv[1] not in ("-", ""):
        return argv[1].strip()
    if len(argv) > 1 and argv[1] == "-" or not sys.stdin.isatty():
        return sys.stdin.read().strip()
    env = os.environ.get("SUPABASE_ACCESS_TOKEN", "").strip()
    if env:
        return env
    return ""


def _decode_claims_unverified(token: str) -> dict:
    try:
        segment = token.split(".")[1]
        segment += "=" * (-len(segment) % 4)
        return json.loads(base64.urlsafe_b64decode(segment))
    except Exception:
        return {}


async def main() -> int:
    print("=" * 68)
    print("DROID — Supabase token verification pre-flight")
    print("=" * 68)

    print(f"\nConfigured posture")
    print(f"  AUTH_REQUIRED     : {settings.auth_required}")
    print(f"  APP_ENV / APP_MODE: {settings.app_env} / {settings.app_mode}")
    print(f"  SUPABASE_URL      : {settings.supabase_url or '(EMPTY)'}")
    print(f"  JWKS endpoint     : {_jwks_url() or '(EMPTY — cannot verify ES256)'}")
    print(f"  SUPABASE_JWT_SECRET set: {bool(settings.supabase_jwt_secret)}")

    if not _jwks_url():
        print(f"\n{BAD} SUPABASE_URL is not set. ES256 tokens cannot be verified.")
        return 1

    # 1. Is the identity provider reachable, and what does it publish?
    print("\nIdentity provider")
    try:
        jwks = await _fetch_jwks(force=True)
    except Exception as exc:
        print(f"  {BAD} JWKS fetch failed: {type(exc).__name__}: {exc}")
        return 1
    keys = jwks.get("keys") or []
    print(f"  {OK} JWKS reachable — {len(keys)} signing key(s)")
    for key in keys:
        print(
            f"      kid={key.get('kid')} kty={key.get('kty')} "
            f"alg={key.get('alg')} crv={key.get('crv')}"
        )
    if not keys:
        print(f"  {BAD} No signing keys published.")
        return 1

    token = _read_token(sys.argv)
    if not token:
        print("\nNo token supplied — provider checks only.")
        print("Pass a token to verify it:  verify_auth_token.py <token>")
        return 0

    # 2. Does the token's header point at a key we hold?
    print("\nToken")
    header = _token_header(token)
    alg = header.get("alg")
    kid = header.get("kid")
    print(f"  alg={alg}  kid={kid}")
    claims = _decode_claims_unverified(token)
    print(f"  aud={claims.get('aud')}  sub={claims.get('sub')}  exp={claims.get('exp')}")
    if claims.get("exp"):
        import time

        remaining = int(claims["exp"]) - int(time.time())
        if remaining <= 0:
            print(f"  {BAD} Token is EXPIRED ({-remaining}s ago) — sign in again and retry.")
            return 1
        print(f"  {OK} Token valid for another {remaining}s")

    selected = _select_jwk(jwks, kid)
    if selected is None:
        print(f"  {BAD} No JWKS key matches kid={kid} — the project has rotated keys.")
        return 1
    print(f"  {OK} Matching signing key found in JWKS")

    # 3. The decisive check: does the real verifier accept it?
    print("\nSignature verification (through app.core.security.decode_supabase_jwt)")
    try:
        payload = await decode_supabase_jwt(token)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        detail = getattr(exc, "detail", str(exc))
        print(f"  {BAD} REJECTED ({status}): {detail}")
        print("\nDo NOT set AUTH_REQUIRED=true — the API would reject this token.")
        return 1

    print(f"  {OK} ACCEPTED — resolved user_id={payload.get('sub')} role={payload.get('role')}")
    print("\nThis token verifies. Setting AUTH_REQUIRED=true is safe for this account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
