"""Set TEST_DATABASE_URL to an asyncpg test database with CREATE SCHEMA access."""

import os
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import interaction, trace
from app.api.dependencies import get_current_user
from app.models.general import Role, Tenant, User, UserTenants
from app.storage.postgres import Base, get_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def timeline_client():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to run PostgreSQL integration tests")

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            # Connection close rolls back the schema, including API session commits.
            await conn.begin()
            schema = f"trace_test_{uuid4().hex}"
            await conn.exec_driver_sql(f"CREATE SCHEMA {schema}")
            await conn.exec_driver_sql(f"SET LOCAL search_path TO {schema}")
            await conn.run_sync(Base.metadata.create_all)
            sessions = async_sessionmaker(
                conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
            )

            async def session_dependency():
                async with sessions() as session:
                    yield session

            async with sessions.begin() as session:
                user = User(
                    full_name="Tester",
                    email="test@example.org",
                    hashed_password="unused",
                )
                role = Role(name="developer")
                tenants = [Tenant(name=n, email=f"{n}@example.org") for n in ("a", "b")]
                session.add_all([user, role, *tenants])
                await session.flush()
                session.add_all(
                    [
                        UserTenants(user_id=user.id, tenant_id=t.id, role_id=role.id)
                        for t in tenants
                    ]
                )

            app = FastAPI()
            app.include_router(interaction.router)
            app.include_router(trace.router)
            app.dependency_overrides[get_session] = session_dependency
            app.dependency_overrides[get_current_user] = lambda: user
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test"
            ) as client:
                yield client, tenants[0].id, tenants[1].id
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_trace_orders_calls_deduplicates_replay_and_isolates_tenants(
    timeline_client,
):
    client, tenant_a, tenant_b = timeline_client
    trace_id = "checkout-42"
    success = dict(
        trace_id=trace_id,
        occurred_at="2026-01-01T00:00:02Z",
        model="example",
        input="hello",
        status="success",
        latency_ms=50,
        input_token=11,
        output_token=7,
    )
    failure = dict(
        success,
        occurred_at="2026-01-01T00:00:01Z",
        status="error",
        input_token=3,
        output_token=0,
    )

    async def submit(tenant, key, payload):
        response = await client.post(
            f"/tenants/{tenant}/interactions",
            json=payload,
            headers={"Idempotency-Key": key},
        )
        assert response.is_success, response.text
        return response.json()["id"]

    # Ingest in reverse event order so the ordering assertion is meaningful.
    second = await submit(tenant_a, "attempt-2", success)
    first = await submit(tenant_a, "attempt-1", failure)
    assert await submit(tenant_a, "attempt-2", success) == second
    await submit(tenant_b, "attempt-1", dict(success, input_token=999))

    response = await client.get(f"/tenants/{tenant_a}/traces/{trace_id}")
    assert response.status_code == 200, response.text
    timeline = response.json()
    assert timeline["tenant_id"] == str(tenant_a)
    assert timeline["trace_id"] == trace_id
    assert [call["id"] for call in timeline["calls"]] == [first, second]
    assert timeline["totals"] == {
        "calls": 2,
        "failures": 1,
        "input_tokens": 14,
        "output_tokens": 7,
    }
