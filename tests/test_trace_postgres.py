"""Set TEST_DATABASE_URL to an asyncpg test database with CREATE SCHEMA access."""

import os
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import interaction, outcome, trace
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
            app.include_router(outcome.router)
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


@pytest.mark.anyio
async def test_trace_search_with_error_includes_successful_retry(timeline_client):
    client, tenant, _ = timeline_client
    calls = [
        ("retried", "error", "00:00:01", 3, 0),
        ("retried", "success", "00:00:02", 11, 7),
        ("healthy", "success", "00:00:01", 50, 20),
    ]
    for trace_id, status, time, inputs, outputs in calls:
        response = await client.post(
            f"/tenants/{tenant}/interactions",
            headers={"Idempotency-Key": f"{trace_id}-{status}"},
            json={
                "trace_id": trace_id,
                "status": status,
                "model": "example",
                "occurred_at": f"2026-01-01T{time}Z",
                "latency_ms": 50,
                "input": "hello",
                "input_token": inputs,
                "output_token": outputs,
            },
        )
        assert response.is_success, response.text

    response = await client.get(
        f"/tenants/{tenant}/traces",
        params={
            "has_error": "true",
            "start_time": "2026-01-01T00:00:00Z",
            "end_time": "2026-01-01T00:01:00Z",
        },
    )
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["total"] == 1
    (summary,) = page["traces"]
    assert summary["trace_id"] == "retried"
    assert summary["call_count"] == 2
    assert summary["failure_count"] == 1
    assert summary["input_tokens"] == 14
    assert summary["output_tokens"] == 7


@pytest.mark.anyio
async def test_outcome_before_call_replay_conflict_and_tenant_isolation(
    timeline_client,
):
    client, tenant_a, tenant_b = timeline_client
    path = f"/tenants/{tenant_a}/outcomes"
    event = dict(
        event_id=str(uuid4()),
        trace_id="shared",
        name="accepted",
        occurred_at="2026-01-07T12:00:00Z",
    )
    created = await client.post(path, json=event)
    assert created.is_success, created.text
    replay = await client.post(path, json=event)
    assert replay.is_success and replay.json() == created.json()
    conflict = await client.post(path, json=dict(event, name="changed"))
    assert conflict.status_code == 409

    for tenant in (tenant_a, tenant_b):
        await submit_search_call(client, tenant, "shared", "model-call")
        detail = await client.get(f"/tenants/{tenant}/traces/shared")
        assert detail.status_code == 200, detail.text
        assert detail.json()["outcomes"] == (
            [created.json()] if tenant == tenant_a else []
        )
        assert detail.json()["totals"]["calls"] == 1


async def submit_search_call(client, tenant, trace_id, key, release="v12"):
    payload = dict(
        trace_id=trace_id,
        release=release,
        model="example",
        input="hello",
        occurred_at="2026-01-05T12:00:00Z",
        status="success",
        latency_ms=25,
        input_token=5,
        output_token=2,
    )
    response = await client.post(
        f"/tenants/{tenant}/interactions",
        json=payload,
        headers={"Idempotency-Key": key},
    )
    assert response.is_success, response.text


@pytest.mark.anyio
async def test_trace_search_matches_late_outcomes_without_multiplying_calls(
    timeline_client,
):
    client, tenant_a, tenant_b = timeline_client
    await submit_search_call(client, tenant_a, "matched", "first")
    await submit_search_call(client, tenant_a, "matched", "second", release="v13")
    await submit_search_call(client, tenant_a, "other", "third")
    path = f"/tenants/{tenant_a}/traces"
    params = dict(
        start_time="2026-01-05T00:00:00Z",
        end_time="2026-01-06T00:00:00Z",
        outcome_name="correction_requested",
        release="v12",
    )

    async def send_outcome(tenant, trace_id, name):
        response = await client.post(
            f"/tenants/{tenant}/outcomes",
            json=dict(
                event_id=str(uuid4()),
                trace_id=trace_id,
                name=name,
                occurred_at="2026-01-07T12:00:00Z",
            ),
        )
        assert response.is_success, response.text

    await send_outcome(tenant_a, "matched", "accepted")
    await send_outcome(tenant_b, "other", "correction_requested")
    before = await client.get(path, params=params)
    assert before.status_code == 200 and before.json()["total"] == 0

    for _ in range(2):
        await send_outcome(tenant_a, "matched", "correction_requested")
    response = await client.get(path, params=params)
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 1
    (summary,) = response.json()["traces"]
    assert summary["trace_id"] == "matched"
    detail = await client.get(f"{path}/matched")
    assert detail.status_code == 200, detail.text
    assert detail.json()["totals"] == {
        "calls": 2,
        "failures": 0,
        "input_tokens": 10,
        "output_tokens": 4,
    }
    assert (
        summary["call_count"],
        summary["failure_count"],
        summary["input_tokens"],
        summary["output_tokens"],
    ) == (2, 0, 10, 4)
