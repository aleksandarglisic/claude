"""
Auth0 JWT validation for the admin panel (Epic E).

This is completely separate from the conversational identity system
(ChatSession.state). Admin auth uses Auth0 JWTs; end-user auth uses
the session state machine. The two must never intersect.

Required environment variables:
  AUTH0_DOMAIN   — e.g. "your-tenant.us.auth0.com"
  AUTH0_AUDIENCE — the API identifier you registered in Auth0,
                   e.g. "https://secureship-api"
"""
import os
from functools import lru_cache

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

AUTH0_DOMAIN = os.getenv("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.getenv("AUTH0_AUDIENCE", "")
ALGORITHMS = ["RS256"]

_security = HTTPBearer()


@lru_cache(maxsize=1)
def _jwks() -> dict:
    """Fetch Auth0 public keys once and cache them for the process lifetime."""
    if not AUTH0_DOMAIN:
        raise RuntimeError(
            "AUTH0_DOMAIN is not set. Add it to docker-compose.yml or your .env file."
        )
    resp = httpx.get(f"https://{AUTH0_DOMAIN}/.well-known/jwks.json", timeout=10)
    resp.raise_for_status()
    return resp.json()


def require_admin(
    credentials: HTTPAuthorizationCredentials = Depends(_security),
) -> dict:
    """FastAPI dependency — validates the Auth0 Bearer JWT and returns its payload.

    Usage:
        @router.get("/admin/customers")
        async def list_customers(payload: dict = Depends(require_admin)):
            ...

    Raises 401 if the token is absent, expired, signed by the wrong key,
    or issued for a different audience/issuer.

    Security note: this check is server-side. Hiding admin routes in the
    frontend nav is NOT sufficient — every admin endpoint must use this dep.
    """
    token = credentials.credentials
    try:
        jwks = _jwks()
        header = jwt.get_unverified_header(token)
        key = next(
            (k for k in jwks["keys"] if k.get("kid") == header.get("kid")),
            None,
        )
        if key is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Signing key not found in Auth0 JWKS",
            )
        payload = jwt.decode(
            token,
            key,
            algorithms=ALGORITHMS,
            audience=AUTH0_AUDIENCE,
            issuer=f"https://{AUTH0_DOMAIN}/",
        )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
