"""
Cognito JWT verification.

Cognito signs access tokens with RS256; the public keys are published at a
well-known JWKS URL per user pool. This verifies a bearer token against
those keys and returns the claims — in particular `cognito:groups`, which
is how "owner" vs "team member" should be modeled (add users to an
"owners" group in the User Pool and check for it in require_owner below).

Untested against a real User Pool yet — verify the JWKS URL and claim
names against your actual pool once it's created (`sam deploy` output will
have the User Pool ID).

LOCAL_DEV=true bypasses all of this — every request is treated as a signed
-in owner, no token required. That's only for running `local_dev.py` on
your own machine to click through the app; it must never be set anywhere
a real request could reach.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

from fastapi import Depends, HTTPException, status

LOCAL_DEV = os.environ.get("LOCAL_DEV", "false").lower() == "true"

if LOCAL_DEV:

    def verify_token() -> dict[str, Any]:
        return {"sub": "local-dev-user", "email": "dev@local.test", "cognito:groups": ["owners"]}

    def require_owner() -> dict[str, Any]:
        return verify_token()

else:
    import requests
    from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
    from jose import jwt

    AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
    USER_POOL_ID = os.environ.get("COGNITO_USER_POOL_ID", "")
    APP_CLIENT_ID = os.environ.get("COGNITO_APP_CLIENT_ID", "")

    _bearer = HTTPBearer()

    @lru_cache
    def _jwks() -> dict[str, Any]:
        url = f"https://cognito-idp.{AWS_REGION}.amazonaws.com/{USER_POOL_ID}/.well-known/jwks.json"
        return requests.get(url, timeout=5).json()

    def _find_key(kid: str) -> dict[str, Any] | None:
        return next((k for k in _jwks().get("keys", []) if k.get("kid") == kid), None)

    def verify_token(credentials: HTTPAuthorizationCredentials = Depends(_bearer)) -> dict[str, Any]:
        token = credentials.credentials
        try:
            header = jwt.get_unverified_header(token)
            key = _find_key(header["kid"])
            if key is None:
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown signing key")
            claims = jwt.decode(token, key, algorithms=["RS256"], audience=APP_CLIENT_ID)
            return claims
        except HTTPException:
            raise
        except Exception as exc:  # noqa: BLE001 — surface as a clean 401, log the real cause
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token") from exc

    def require_owner(claims: dict[str, Any] = Depends(verify_token)) -> dict[str, Any]:
        groups = claims.get("cognito:groups", [])
        if "owners" not in groups:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Owner access required")
        return claims
