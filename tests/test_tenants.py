from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.models.general import Tenant, User
from app.storage.postgres import get_session
from app.utils.token import create_access_token

PAYLOAD = {"name": " Example ", "email": "contact@example.com"}


@pytest.fixture
def tenant_client(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRY_MINS", "15")
    monkeypatch.setenv("REFRESH_TOKEN_EXPIRY_DAYS", "7")
    monkeypatch.setenv(
        "JWT_SECRET_KEY", "tenant-tests-only-secret-with-at-least-32-characters"
    )
    user = User(id=uuid4(), is_active=True)
    tenant = Tenant(id=uuid4(), name="Example", email=PAYLOAD["email"])
    admin_id = uuid4()
    db = AsyncMock()
    db.add = Mock()
    db.get.return_value = user
    db.scalar.return_value = admin_id
    db.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=tenant))

    async def override_session():
        yield db

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer " + create_access_token(
        str(user.id), True
    )
    try:
        yield client, db, user, tenant, admin_id
    finally:
        client.close()
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_creator_gets_admin_membership_before_commit(tenant_client):
    client, db, user, tenant, admin_id = tenant_client

    async def check_commit():
        membership = db.add.call_args.args[0]
        assert membership.user_id == user.id
        assert membership.tenant_id == tenant.id
        assert membership.role_id == admin_id

    db.commit.side_effect = check_commit
    response = client.post("/tenants", json=PAYLOAD)
    assert response.status_code == 201
    assert response.json()["id"] == str(tenant.id)
    db.get.assert_awaited_once_with(User, user.id)
    params = db.execute.call_args.args[0].compile().params
    assert params["name"] == "Example"
    assert params["phone"] is None
    assert "admin" in db.scalar.call_args.args[0].compile().params.values()
    db.commit.assert_awaited_once()
    db.rollback.assert_not_awaited()


@pytest.mark.parametrize("kind", ["missing", "invalid", "expired", "bad_subject"])
def test_invalid_token_cannot_create_tenant(tenant_client, kind):
    client, db, user, _, _ = tenant_client
    if kind == "missing":
        del client.headers["Authorization"]
    elif kind == "invalid":
        client.headers["Authorization"] = "Bearer garbage"
    else:
        token = create_access_token(
            "not-a-uuid" if kind == "bad_subject" else str(user.id),
            True,
            expires_delta=timedelta(seconds=-1) if kind == "expired" else None,
        )
        client.headers["Authorization"] = "Bearer " + token
    response = client.post("/tenants", json=PAYLOAD)
    assert response.status_code == 401
    db.get.assert_not_awaited()
    db.execute.assert_not_awaited()


@pytest.mark.parametrize("deleted", [True, False])
def test_current_database_account_status_is_checked(tenant_client, deleted):
    client, db, user, _, _ = tenant_client
    if deleted:
        db.get.return_value = None
    else:
        user.is_active = False
    response = client.post("/tenants", json=PAYLOAD)
    assert response.status_code == (401 if deleted else 403)
    db.execute.assert_not_awaited()


def test_missing_admin_role_creates_nothing(tenant_client):
    client, db, *_ = tenant_client
    db.scalar.return_value = None
    assert client.post("/tenants", json=PAYLOAD).status_code == 503
    db.execute.assert_not_awaited()
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


def test_duplicate_email_adds_no_membership(tenant_client):
    client, db, *_ = tenant_client
    db.execute.return_value.scalar_one_or_none.return_value = None
    assert client.post("/tenants", json=PAYLOAD).status_code == 409
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


def test_membership_failure_rolls_back_tenant(tenant_client):
    client, db, *_ = tenant_client
    db.commit.side_effect = IntegrityError("INSERT user_tenant", {}, Exception())
    with pytest.raises(IntegrityError):
        client.post("/tenants", json=PAYLOAD)
    db.add.assert_called_once()
    db.rollback.assert_awaited_once()


@pytest.mark.parametrize(
    "extra",
    [
        {"creator_id": str(uuid4())},
        {"role_id": str(uuid4())},
        {"owner_email": "someone@example.com"},
        {"name": "   "},
    ],
)
def test_request_cannot_choose_owner_or_role(tenant_client, extra):
    client, db, *_ = tenant_client
    assert client.post("/tenants", json={**PAYLOAD, **extra}).status_code == 422
    db.execute.assert_not_awaited()
