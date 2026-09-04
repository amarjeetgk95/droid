from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from app.core.config import settings
import structlog

logger = structlog.get_logger()
security_scheme = HTTPBearer(auto_error=False)

class AuthUser:
    def __init__(self, user_id: str, email: str | None = None, role: str = "user"):
        self.user_id = user_id
        self.email = email
        self.role = role

def decode_supabase_jwt(token: str) -> dict:
    """Decode and validate a Supabase JWT token."""
    if not settings.supabase_jwt_secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication not configured"
        )
    try:
        payload = jwt.decode(
            token,
            settings.supabase_jwt_secret,
            algorithms=["HS256"],
            audience="authenticated"
        )
        return payload
    except JWTError as e:
        logger.warning("jwt_decode_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security_scheme)
) -> AuthUser | None:
    """Get the current authenticated user, or None in dev mode."""
    # If credentials provided, try to decode Supabase JWT token
    if credentials is not None and credentials.credentials:
        try:
            payload = decode_supabase_jwt(credentials.credentials)
            return AuthUser(
                user_id=payload.get("sub", ""),
                email=payload.get("email"),
                role=payload.get("role", "user")
            )
        except Exception as e:
            if settings.auth_required:
                raise
            logger.debug("dev_auth_token_ignored", error=str(e))

    # Development mode: auth not required — use deterministic UUID so DB queries succeed
    if not settings.auth_required:
        return AuthUser(user_id="00000000-0000-0000-0000-000000000001", email="dev@localhost", role="admin")
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    
    payload = decode_supabase_jwt(credentials.credentials)
    return AuthUser(
        user_id=payload.get("sub", ""),
        email=payload.get("email"),
        role=payload.get("role", "user")
    )

async def require_auth(
    user: AuthUser | None = Depends(get_current_user)
) -> AuthUser:
    """Dependency that requires authentication."""
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )
    return user
