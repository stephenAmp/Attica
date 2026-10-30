from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from app.core.config import Settings


def create_access_token(
    subject: str,
    is_active: bool,
    tenant: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    settings = Settings()
    now = datetime.now(timezone.utc)
    lifetime = (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.acces_token_expiry_mins)
    )
    payload = {
        "sub": subject,
        "exp": now + lifetime,
        "iat": now,
        "is_active": is_active,
        "iss": "attica",
        "aud": "tenant",
        "token_type": "access",
    }
    # Login proves identity; tenant authorization is checked separately.
    if tenant is not None:
        payload["tenant"] = tenant
    return jwt.encode(payload, settings.jwt_secret_key, algorithm="HS256")


def create_refresh_token(
    subject: str,
    is_active: bool,
    tenant: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    if expires_delta:
        expires = datetime.now(timezone.utc) + expires_delta
    expires = datetime.now(timezone.utc) + Settings.refresh_token_expiry_days

    payload = {
        "sub": str(subject),
        "tenant": str(tenant),
        "is_active": is_active,
        "exp": expires,
        "aud": "tenant",
        "iss": "attica",
        "token_type": "refresh",
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(payload, Settings.jwt_secret_key, algorithm="HS256")
    return token


def decode_token(token: str) -> Dict[str, Any]:
    payload = jwt.decode(
        token,
        Settings().jwt_secret_key,
        algorithms=["HS256"],
        issuer="attica",
        audience="tenant",
        options={"require": ["sub", "exp", "iat", "token_type"]},
    )
    if payload["token_type"] != "access":
        raise jwt.InvalidTokenError("Expected an access token")
    return payload
