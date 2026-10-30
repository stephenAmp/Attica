from datetime import timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.general import User
from app.storage.postgres import get_session
from app.utils.security import hash_password
from app.utils.token import create_access_token, decode_token

PASSWORD = "a-long-test-password"
PAYLOAD = {"email": "Stephen@Example.com", "password": PASSWORD}
SECRET = "a-test-only-secret-key-with-at-least-32-characters"


@pytest.fixture(autouse=True)
def token_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRY_MINS", "15")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRY_DAYS", "7")
    monkeypatch.setenv("JWT_SECRET_KEY", SECRET)


@pytest.fixture
def login_client():
    user = User(
        id=uuid4(),
        full_name="Stephen",
        email="stephen@example.com",
        hashed_password=hash_password(PASSWORD),
        is_active=True,
    )
    session = AsyncMock()
    session.scalar.return_value = user

    async def override_session():
        yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    try:
        yield client, session, user
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_login_returns_expiring_identity_token(login_client):
    client, session, user = login_client
    response = client.post("/auth/login", json=PAYLOAD)
    assert response.status_code == 200
    assert set(response.json()) == {"access_token", "token_type"}
    assert response.json()["token_type"] == "bearer"
    claims = decode_token(response.json()["access_token"])
    assert claims["sub"] == str(user.id)
    assert claims["exp"] - claims["iat"] == 15 * 60
    assert claims["token_type"] == "access"
    assert "tenant" not in claims
    assert "role" not in claims
    assert "password" not in claims
    assert "hashed_password" not in claims
    query = session.scalar.call_args.args[0]
    assert "stephen@example.com" in query.compile().params.values()
    session.commit.assert_not_awaited()


@pytest.mark.parametrize("unknown_user", [True, False])
def test_invalid_credentials_have_same_response(login_client, unknown_user):
    client, session, _ = login_client
    if unknown_user:
        session.scalar.return_value = None
    response = client.post("/auth/login", json={**PAYLOAD, "password": "wrong"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid email or password"}
    assert response.headers["www-authenticate"] == "Bearer"


def test_inactive_user_cannot_login(login_client):
    client, _, user = login_client
    user.is_active = False
    response = client.post("/auth/login", json=PAYLOAD)
    assert response.status_code == 403
    assert "access_token" not in response.json()


def test_expired_token_is_rejected():
    token = create_access_token("user-id", True, expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(token)


@pytest.mark.parametrize(
    "change",
    [
        {"aud": "another-api"},
        {"iss": "another-issuer"},
        {"token_type": "refresh"},
    ],
)
def test_wrong_claims_are_rejected(change):
    claims = decode_token(create_access_token("user-id", True))
    token = jwt.encode({**claims, **change}, SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(token)


def test_invalid_signature_is_rejected():
    claims = decode_token(create_access_token("user-id", True))
    token = jwt.encode(
        claims, "different-test-secret-at-least-32-chars", algorithm="HS256"
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(token)
