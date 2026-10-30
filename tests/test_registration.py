from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.general import User
from app.storage.postgres import get_session
from app.utils.security import verify_password

PASSWORD = "a-long-test-password"
PAYLOAD = {
    "full_name": " Stephen Test ",
    "email": " Stephen@Example.com ",
    "password": PASSWORD,
}


@pytest.fixture
def registration_client():
    session = AsyncMock()

    async def override_session():
        yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = override_session
    # The database dependency is replaced; no engine startup is needed here.
    client = TestClient(app)
    try:
        yield client, session
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_register_hashes_password_and_returns_public_fields(registration_client):
    client, session = registration_client
    stored = {}

    async def insert_user(statement):
        stored.update(statement.compile().params)
        user = User(
            id=uuid4(),
            full_name=stored["full_name"],
            email=stored["email"],
            hashed_password=stored["hashed_password"],
            is_active=True,
        )
        return Mock(scalar_one_or_none=Mock(return_value=user))

    session.execute.side_effect = insert_user
    response = client.post("/auth/register", json=PAYLOAD)

    assert response.status_code == 201
    assert response.json()["email"] == "stephen@example.com"
    assert response.json()["full_name"] == "Stephen Test"
    assert set(response.json()) == {"id", "full_name", "email", "is_active"}
    assert stored["hashed_password"] != PASSWORD
    assert verify_password(PASSWORD, stored["hashed_password"])
    assert len(stored["hashed_password"]) <= 100  # Existing database column limit.
    session.commit.assert_awaited_once()


def test_existing_email_returns_conflict(registration_client):
    client, session = registration_client
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=None))

    response = client.post("/auth/register", json=PAYLOAD)

    assert response.status_code == 409
    session.commit.assert_not_awaited()


@pytest.mark.parametrize(
    "changes",
    [
        {"email": "invalid"},
        {"password": "short"},
        {"password": "x" * 129},
        {"full_name": "   "},
        {"full_name": "x" * 101},
        {"role": "admin"},
        {"is_active": True},
    ],
)
def test_invalid_registration_does_not_write(registration_client, changes):
    client, session = registration_client

    response = client.post("/auth/register", json={**PAYLOAD, **changes})

    assert response.status_code == 422
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_commit_failure_does_not_return_success(registration_client):
    client, session = registration_client
    session.execute.return_value = Mock(
        scalar_one_or_none=Mock(
            return_value=User(
                id=uuid4(),
                full_name="Stephen",
                email="stephen@example.com",
                is_active=True,
            )
        )
    )
    session.commit.side_effect = RuntimeError("database commit failed")

    with pytest.raises(RuntimeError, match="database commit failed"):
        client.post("/auth/register", json=PAYLOAD)
