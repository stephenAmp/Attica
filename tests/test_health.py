from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import app
from app.storage.postgres import get_session


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+asyncpg://test:test@127.0.0.1:5432/test"
    )
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_liveness(client):
    response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize("available", [True, False])
def test_readiness(client, available):
    session = AsyncMock()
    if not available:
        session.execute.side_effect = OperationalError("SELECT 1", {}, Exception())

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    response = client.get("/health/ready")
    assert response.status_code == (200 if available else 503)
    assert response.json() == (
        {"status": "ok"} if available else {"detail": "Database unavailable"}
    )
    session.execute.assert_awaited_once()
