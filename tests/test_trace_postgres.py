"""Set TEST_DATABASE_URL to an asyncpg test database with CREATE SCHEMA access."""

import os
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api import ingestion_keys, interaction, outcome, release, trace
from app.utils.token import create_access_token
from app.models.general import (
    IngestionAPIKey,
    Interaction,
    OutboxEvent,
    ProcessedEvent,
    Role,
    Tenant,
    User,
    UserTenants,
)
from app.schema.interaction import InteractionEvent
from app.workers.process_event import process_event
from app.storage.postgres import Base, get_session


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def timeline_db_client():
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
            app.include_router(release.router)
            app.include_router(outcome.router)
            app.dependency_overrides[get_session] = session_dependency
            app.include_router(ingestion_keys.router)
            token = create_access_token(str(user.id), True)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app), base_url="http://test",
                headers={"Authorization": f"Bearer {token}"},
            ) as client:
                yield client, tenants[0].id, tenants[1].id, sessions
    finally:
        await engine.dispose()


@pytest.fixture
def timeline_client(timeline_db_client):
    client, tenant_a, tenant_b, _ = timeline_db_client
    return client, tenant_a, tenant_b


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


@pytest.mark.anyio
async def test_metadata_only_failed_call_and_outcome(timeline_db_client):
    client, tenant, _, sessions = timeline_db_client
    path = f"/tenants/{tenant}"
    payload = dict(
        trace_id="metadata-only",
        occurred_at="2026-01-05T12:00:00Z",
        status="error",
        model="example",
        latency_ms=18,
        input_token=9,
        output_token=2,
    )
    headers = {"Idempotency-Key": "failed-call"}
    created = await client.post(f"{path}/interactions", json=payload, headers=headers)
    assert created.is_success, created.text
    replay = await client.post(f"{path}/interactions", json=payload, headers=headers)
    assert replay.is_success and replay.json() == created.json()
    call_id = UUID(created.json()["id"])

    async with sessions() as db:
        call = await db.get(Interaction, call_id)
        assert call.source_type == "user"
        assert call.source_id == call.created_by
        assert call.input is None and call.output is None
        row = (await db.scalars(select(OutboxEvent))).one()
        assert row.payload.get("input") is None and row.payload.get("output") is None
        event = InteractionEvent.model_validate(row.payload)
        assert event.interaction_id == call_id

    async with sessions() as db:
        assert await process_event(db, event)
        summary = (await db.scalars(select(ProcessedEvent))).one()
        assert summary.output_empty is None and summary.is_error is True
        assert summary.total_tokens == 11

    outcome = dict(
        event_id=str(uuid4()),
        trace_id=payload["trace_id"],
        occurred_at=payload["occurred_at"],
        name="review_requested",
    )
    recorded = await client.post(f"{path}/outcomes", json=outcome)
    assert recorded.is_success, recorded.text
    timeline = await client.get(f"{path}/traces/metadata-only")
    assert timeline.status_code == 200, timeline.text
    trace_data = timeline.json()
    assert [c["id"] for c in trace_data["calls"]] == [str(call_id)]
    assert trace_data["totals"] == dict(
        calls=1, failures=1, input_tokens=9, output_tokens=2
    )
    assert trace_data["outcomes"] == [recorded.json()]


@pytest.mark.anyio
async def test_ingestion_key_lifecycle(timeline_db_client):
    client, tenant, other, sessions = timeline_db_client
    base = f"/tenants/{tenant}"
    keys = f"{base}/ingestion-keys"
    name = {"name": "support-api-prod"}
    assert (await client.post(keys, json=name)).status_code == 403

    async with sessions.begin() as db:
        membership = (await db.scalars(select(UserTenants).where(UserTenants.tenant_id == tenant))).one()
        admin = Role(name="admin")
        db.add(admin)
        await db.flush()
        membership.role_id = admin.id
        issuer = membership.user_id

    issued = await client.post(keys, json=name)
    assert issued.status_code == 201, issued.text
    first = issued.json()
    second = (await client.post(keys, json={"name": "second"})).json()
    listed = (await client.get(keys)).json()
    assert len(listed) == 2
    assert all("api_key" not in row and "secret_hash" not in row for row in listed)
    async with sessions() as db:
        stored = await db.get(IngestionAPIKey, UUID(first["id"]))
        assert stored.created_by == issuer
        assert stored.secret_hash not in first["api_key"]

    admin_auth = client.headers.pop("Authorization")
    client.headers["X-Attica-API-Key"] = first["api_key"]
    payload = dict(trace_id="key-trace", occurred_at="2026-01-01T00:00:00Z",
                   model="example", status="success", latency_ms=20, input_token=2, output_token=1)
    headers = {"Idempotency-Key": "attempt-1"}
    created = await client.post(f"{base}/interactions", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["source_type"] == "api_key"
    assert created.json()["source_id"] == first["id"]
    assert created.json()["ingestion_key_id"] == first["id"]
    assert created.json()["created_by"] is None
    event = dict(trace_id="key-trace", occurred_at="2026-01-01T00:01:00Z", event_id=str(uuid4()), name="resolved")
    assert (await client.post(f"{base}/outcomes", json=event)).status_code == 200
    assert (await client.get(f"{base}/traces/key-trace")).status_code == 401
    assert (await client.post(keys, json=name)).status_code == 401
    assert (await client.post(f"/tenants/{other}/outcomes", json=event)).status_code == 403
    assert (await client.post(f"/tenants/{other}/interactions", json=payload, headers=headers)).status_code == 403

    for _ in range(4):
        assert (await client.post(f"{base}/interactions", json=payload, headers=headers)).status_code == 201
    client.headers["X-Attica-API-Key"] = second["api_key"]
    assert (await client.post(f"{base}/interactions", json=payload, headers=headers)).status_code == 429

    del client.headers["X-Attica-API-Key"]
    revoked = await client.delete(f"{keys}/{first['id']}", headers={"Authorization": admin_auth})
    assert revoked.status_code == 204
    client.headers["X-Attica-API-Key"] = first["api_key"]
    assert (await client.post(f"{base}/outcomes", json=event)).status_code == 401


@pytest.mark.anyio
async def test_batch_replay_in_new_order_deduplicates_interactions_and_outbox(timeline_db_client):
    client, tenant, _, sessions = timeline_db_client
    path = f"/tenants/{tenant}/interactions/batch"
    payload = dict(
        occurred_at="2026-11-25T12:30:00Z", model="example", status="success",
        latency_ms=50, input_token=3, output_token=2,
    )
    a, b, c, d = [
        {"idempotency_key": key, "interaction": payload}
        for key in ("attempt-a", "attempt-b", "attempt-c", "attempt-d")
    ]

    first = await client.post(path, json={"items": [a, b, c]})
    assert first.status_code == 201, first.text
    assert [(r["index"], r["status"]) for r in first.json()["result"]] == [
        (0, "created"), (1, "created"), (2, "created"),
    ]

    # The client can retry using the original events alone, even if it lost the response.
    retry = await client.post(path, json={"items": [c, a, d]})
    assert retry.status_code == 201, retry.text

    async with sessions() as db:
        stored = dict((await db.execute(
            select(Interaction.idempotency_key, Interaction.id).where(Interaction.tenant_id == tenant)
        )).all())
        outbox_ids = (await db.scalars(
            select(OutboxEvent.interaction_id).where(OutboxEvent.tenant_id == tenant)
        )).all()

    assert set(stored) == {item["idempotency_key"] for item in (a, b, c, d)}
    assert sorted(outbox_ids) == sorted(stored.values())
    assert retry.json()["result"] == [
        {"index": index, "interaction_id": str(stored[item["idempotency_key"]]), "status": status}
        for index, (item, status) in enumerate([(c, "duplicate"), (a, "duplicate"), (d, "created")])
    ]


@pytest.mark.anyio
async def test_release_comparison_and_failure_drilldown(timeline_db_client):
    from datetime import datetime, timedelta, timezone

    client, tenant, other, sessions = timeline_db_client
    start = datetime(2026, 11, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    async with sessions.begin() as db:
        user_id = (await db.scalars(select(User.id))).one()

        def call(trace, release, *, at=start, status="success", owner=tenant,
                 feature="chat", environment="prod"):
            db.add(Interaction(
                tenant_id=owner, created_by=user_id, trace_id=trace, release=release,
                feature=feature, environment=environment, occurred_at=at, status=status,
                idempotency_key=str(uuid4()), payload_hash="0" * 64, model="example",
                input_token=100, output_token=20, latency_ms=12,
            ))

        for i in range(10):
            call(f"a{i}", "A")
            call(f"b{i}", "B", status="error" if i < 3 else "success")
            call(f"b{i}", "B", at=end if i == 0 else start + timedelta(seconds=1))
        call("b4", "B", owner=other, status="error")
        call("before", "B", at=start - timedelta(seconds=1))
        call("before", "B", status="error")
        call("at-end", "B", at=end, status="error")
        call("mixed", "A", status="error")
        call("mixed", "B")
        call("other-feature", "B", feature="search", status="error")
        call("other-env", "B", environment="dev", status="error")

    base = f"/tenants/{tenant}"
    params = dict(baseline_release="A", candidate_release="B", feature="chat",
                  environment="prod", start_time=start.isoformat(), end_time=end.isoformat())
    path = f"{base}/releases/compare"
    response = await client.get(path, params=params)
    assert response.status_code == 200, response.text
    result = response.json()
    baseline = dict(trace_count=10, call_count=10, traces_with_failed_calls=0,
                    failed_call_trace_rate=0, calls_per_trace=1, input_tokens_per_trace=100,
                    output_tokens_per_trace=20, input_tokens_per_call=100, output_tokens_per_call=20)
    assert result["baseline"] == baseline
    assert result["candidate"] == dict(baseline, call_count=20, traces_with_failed_calls=3,
                                       failed_call_trace_rate=0.3, calls_per_trace=2,
                                       input_tokens_per_trace=200, output_tokens_per_trace=40)
    assert result["change"] == dict(trace_count=0, call_count=10, traces_with_failed_calls=3,
                                    failed_call_trace_rate_pp=30, calls_per_trace=1, input_tokens_per_trace=100,
                                    output_tokens_per_trace=20, input_tokens_per_call=0, output_tokens_per_call=0)
    assert result["excluded_ambiguous_traces"] == 1

    async def failures(comparison):
        response = await client.get(f"{base}/traces", params=comparison["candidate_drilldown"])
        assert response.status_code == 200, response.text
        page = response.json()
        assert page["total"] == comparison["candidate"]["traces_with_failed_calls"]
        return {trace["trace_id"] for trace in page["traces"]}

    assert await failures(result) == {"b0", "b1", "b2"}
    async with sessions.begin() as db:
        call("late-error", "B")
        call("late-error", "B", at=end + timedelta(seconds=1), status="error")

    response = await client.get(path, params=dict(params, baseline_release="missing"))
    assert response.status_code == 200, response.text
    empty = response.json()
    counts = {"trace_count", "call_count", "traces_with_failed_calls"}
    assert empty["baseline"] == {k: 0 if k in counts else None for k in baseline}
    assert empty["change"]["failed_call_trace_rate_pp"] is None
    assert await failures(empty) == {"b0", "b1", "b2", "late-error"}
