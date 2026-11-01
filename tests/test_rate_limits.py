import asyncio
from uuid import UUID

import httpx
import pytest
from fastapi import Depends, FastAPI, Request

from app.api import dependencies
from app.models.general import UserTenants

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(params=["ip", "tenant"])
async def limiter_client(request, monkeypatch):
    # Replace dictionaries so tests never consume another test's allowance.
    monkeypatch.setattr(dependencies, "request_counters", {})
    monkeypatch.setattr(dependencies, "tenant_request_counters", {})
    clock = [1000]
    monkeypatch.setattr(dependencies.time, "time", lambda: clock[0])
    kind = request.param
    limiter = (
        dependencies.RateLimiter(5, 60)
        if kind == "ip"
        else dependencies.TenantSpecificRateLimiter(5, 60)
    )
    app = FastAPI()

    async def membership(request: Request):
        return UserTenants(
            tenant_id=UUID(request.headers.get("x-test-tenant", str(UUID(int=1))))
        )

    app.dependency_overrides[dependencies.get_tenant_membership] = membership

    @app.get("/items/{item_id}", dependencies=[Depends(limiter)])
    @app.get("/other", dependencies=[Depends(limiter)])
    async def endpoint():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app, client=("127.0.0.1", 1000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, clock, kind, app


async def test_limit_and_retry_after(limiter_client):
    client, _, _, _ = limiter_client
    for _ in range(5):
        assert (await client.get("/items/1")).status_code == 200
    response = await client.get("/items/1")
    assert response.status_code == 429
    assert response.json() == {"detail": "Too Many Requests"}
    assert response.headers["Retry-After"] == "60"


async def test_resets_at_exact_window_boundary(limiter_client):
    client, clock, _, _ = limiter_client
    for _ in range(5):
        await client.get("/items/1")
    clock[0] = 1059
    response = await client.get("/items/1")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "1"
    clock[0] = 1060
    for _ in range(5):
        assert (await client.get("/items/1")).status_code == 200
    assert (await client.get("/items/1")).status_code == 429


async def test_concurrent_requests_respect_limit(limiter_client):
    client, _, _, _ = limiter_client
    responses = await asyncio.gather(*(client.get("/items/1") for _ in range(30)))
    assert sum(response.status_code == 200 for response in responses) == 5
    assert sum(response.status_code == 429 for response in responses) == 25


async def test_other_client_or_tenant_keeps_own_allowance(limiter_client):
    client, _, kind, app = limiter_client
    for _ in range(5):
        await client.get("/items/1")
    assert (await client.get("/items/1")).status_code == 429
    if kind == "tenant":
        # Same IP, different authenticated tenant.
        response = await client.get(
            "/items/1", headers={"x-test-tenant": str(UUID(int=2))}
        )
    else:
        transport = httpx.ASGITransport(app=app, client=("127.0.0.2", 1000))
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as other:
            response = await other.get("/items/1")
    assert response.status_code == 200


async def test_routes_have_separate_allowances(limiter_client):
    client, _, _, _ = limiter_client
    for _ in range(5):
        await client.get("/items/1")
    assert (await client.get("/items/1")).status_code == 429
    assert (await client.get("/other")).status_code == 200


async def test_expired_entries_are_cleaned_at_boundary(limiter_client):
    client, clock, kind, _ = limiter_client
    await client.get("/items/1")
    counters = (
        dependencies.request_counters
        if kind == "ip"
        else dependencies.tenant_request_counters
    )
    original_keys = set(counters)
    assert len(original_keys) == 1
    clock[0] = 1060
    assert (await client.get("/other")).status_code == 200
    assert original_keys.isdisjoint(counters)


async def test_tenant_limit_covers_different_items_and_ips(limiter_client):
    client, _, kind, app = limiter_client
    if kind != "tenant":
        pytest.skip("Tenant quotas aggregate across item IDs and client IPs")
    for item_id in range(5):
        assert (await client.get(f"/items/{item_id}")).status_code == 200
    transport = httpx.ASGITransport(app=app, client=("127.0.0.2", 1000))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as other:
        assert (await other.get("/items/99")).status_code == 429
