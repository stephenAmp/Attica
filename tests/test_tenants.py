from datetime import timedelta
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import app
from app.models.general import Tenant, User, UserTenants
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


def configure_member_lookup(db, user, tenant, admin_id):
    async def lookup(model, key):
        if model is User and key == user.id:
            return user
        if model is UserTenants and key == {"user_id": user.id, "tenant_id": tenant.id}:
            return UserTenants(user_id=user.id, tenant_id=tenant.id, role_id=admin_id)
        if model is Tenant and key == tenant.id:
            return tenant
        return None

    db.get.side_effect = lookup


def test_member_can_read_their_tenant(tenant_client):
    client, db, user, tenant, admin_id = tenant_client
    configure_member_lookup(db, user, tenant, admin_id)
    response = client.get(f"/tenants/{tenant.id}")
    assert response.status_code == 200
    assert response.json()["id"] == str(tenant.id)
    assert db.get.await_count == 3
    db.commit.assert_not_awaited()


def test_membership_in_one_tenant_does_not_allow_another(tenant_client):
    client, db, user, tenant, admin_id = tenant_client
    configure_member_lookup(db, user, tenant, admin_id)
    other_tenant = uuid4()
    response = client.get(f"/tenants/{other_tenant}")
    assert response.status_code == 404
    assert response.json() == {"detail": "Tenant not found"}
    assert not any(call.args[0] is Tenant for call in db.get.await_args_list)


def test_another_users_membership_does_not_grant_access(tenant_client):
    client, db, user, tenant, admin_id = tenant_client
    configure_member_lookup(db, user, tenant, admin_id)
    stranger = User(id=uuid4(), is_active=True)
    original_lookup = db.get.side_effect

    async def lookup(model, key):
        if model is User and key == stranger.id:
            return stranger
        return await original_lookup(model, key)

    db.get.side_effect = lookup
    client.headers["Authorization"] = "Bearer " + create_access_token(
        str(stranger.id), True
    )
    assert client.get(f"/tenants/{tenant.id}").status_code == 404
    assert not any(call.args[0] is Tenant for call in db.get.await_args_list)


def test_removed_membership_is_rechecked_with_same_token(tenant_client):
    client, db, user, tenant, admin_id = tenant_client
    configure_member_lookup(db, user, tenant, admin_id)
    assert client.get(f"/tenants/{tenant.id}").status_code == 200
    original_lookup = db.get.side_effect

    async def lookup(model, key):
        if model is UserTenants:
            return None
        return await original_lookup(model, key)

    db.get.side_effect = lookup
    assert client.get(f"/tenants/{tenant.id}").status_code == 404


def test_tenant_read_requires_authentication(tenant_client):
    client, db, _, tenant, _ = tenant_client
    del client.headers["Authorization"]
    assert client.get(f"/tenants/{tenant.id}").status_code == 401
    db.get.assert_not_awaited()


def test_tenant_id_must_be_uuid(tenant_client):
    client, db, *_ = tenant_client
    assert client.get("/tenants/not-a-uuid").status_code == 422
    assert not any(call.args[0] is UserTenants for call in db.get.await_args_list)
