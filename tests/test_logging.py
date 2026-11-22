import asyncio
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import httpx
import pytest
import structlog
from fastapi import FastAPI, HTTPException
from structlog.testing import capture_logs

import app.api.middleware.request_logging as middleware
from app.api.middleware.request_size import RequestSizeLimitMiddleware
from app.schema.interaction import InteractionCreate, InteractionRead
from app.services.interaction import InteractionService


@pytest.fixture(autouse=True)
def fresh_logger(monkeypatch):
    monkeypatch.setattr(middleware, "logger", structlog.get_logger())


def test_concurrent_requests_keep_context_and_hide_paths():
    app = FastAPI()
    app.add_middleware(middleware.RequestLoggingMiddleware)

    @app.get("/items/{item}")
    async def endpoint(item: str):
        structlog.contextvars.bind_contextvars(tenant_id=item)
        await asyncio.sleep(0)
        return {}

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(
                client.get("/items/tenant-a"), client.get("/items/tenant-b")
            )
            await client.get("/private-secret?token=secret")
        assert len({r.headers["x-request-id"] for r in responses}) == 2
        assert structlog.contextvars.get_contextvars() == {}
        return responses

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        responses = asyncio.run(check())
    for tenant, response in zip(("tenant-a", "tenant-b"), responses):
        record = next(
            r for r in logs if r["request_id"] == response.headers["x-request-id"]
        )
        assert record["tenant_id"] == tenant
        assert record["route"] == "/items/{item}"
    assert logs[-1]["route"] == "unmatched"
    assert "tenant_id" not in logs[-1]
    assert "private-secret" not in json.dumps(logs)


@pytest.mark.parametrize("status", [401, 413, 422, 429, 500])
def test_error_responses_have_request_ids(status):
    app = FastAPI()
    app.add_middleware(RequestSizeLimitMiddleware)
    app.add_middleware(middleware.RequestLoggingMiddleware)

    @app.post("/")
    async def endpoint(body: dict):
        if status == 500:
            raise RuntimeError("private-secret")
        raise HTTPException(status)

    async def check():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://test"
        ) as client:
            if status == 413:
                response = await client.post("/", content=b"x" * 65537)
            elif status == 422:
                response = await client.post("/", content=b"not-json")
            else:
                response = await client.post("/", json={})
            assert response.status_code == status
            assert response.headers["x-request-id"]
            assert structlog.contextvars.get_contextvars() == {}

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        asyncio.run(check())
    assert logs[-1]["status"] == status
    assert sum(r["event"] == "unhandled_request_exception" for r in logs) == (
        status == 500
    )


def test_stream_failure_is_not_reported_as_success():
    async def endpoint(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send(
            {"type": "http.response.body", "body": b"partial", "more_body": True}
        )
        raise RuntimeError("stream failed")

    async def check():
        with pytest.raises(RuntimeError):
            await middleware.RequestLoggingMiddleware(endpoint)(
                {"type": "http", "method": "GET"}, AsyncMock(), AsyncMock()
            )
        assert structlog.contextvars.get_contextvars() == {}

    with capture_logs(processors=[structlog.contextvars.merge_contextvars]) as logs:
        asyncio.run(check())
    assert logs[-1]["status"] == 200
    assert logs[-1]["outcome"] == "server_error"
    assert logs[-1]["response_complete"] is False
    assert len(logs) == 1  # Server owns the propagated exception log.


def test_cleanup_even_if_summary_logging_fails(monkeypatch):
    class BrokenLogger:
        def info(self, *args, **kwargs):
            raise OSError("log sink failed")

    monkeypatch.setattr(middleware, "logger", BrokenLogger())

    async def endpoint(scope, receive, send):
        structlog.contextvars.bind_contextvars(tenant_id="tenant-a")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def check():
        with pytest.raises(OSError):
            await middleware.RequestLoggingMiddleware(endpoint)(
                {"type": "http", "method": "GET"}, AsyncMock(), AsyncMock()
            )
        assert structlog.contextvars.get_contextvars() == {}

    asyncio.run(check())


def test_production_logs_are_json_and_exception_data_is_private():
    code = """
import logging
import structlog
from app.core.logging import configure_logging
configure_logging()
structlog.get_logger().info("application_event")
logging.getLogger("library").info("library_event")
logging.getLogger("uvicorn.error").info("server_event")
logging.getLogger("uvicorn.access").info("duplicate_access")
try:
    raise ValueError("private-secret")
except ValueError:
    structlog.get_logger().exception("application_failure")
    logging.getLogger("uvicorn.error").exception("server_failure")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", code],
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, "APP_ENV": "production"},
    )
    records = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(records) == 5
    assert not result.stderr
    assert "private-secret" not in result.stdout
    for record in records:
        assert record["level"]
        assert record["timestamp"]
    for record in records[-2:]:
        assert record["exception"]["type"] == "ValueError"
        assert record["exception"]["frames"]


@pytest.mark.parametrize("existing", [False, True])
def test_ingestion_outcomes(existing):
    now = datetime.now(timezone.utc)
    data = InteractionCreate(
        occurred_at=now,
        status="success",
        model="test",
        latency_ms=1,
        input_token=1,
        output_token=1,
        input="private prompt",
        output="private reply",
    )
    from app.utils.security import hash_payload

    user_id = uuid4()
    record = SimpleNamespace(
        **data.model_dump(),
        id=uuid4(),
        tenant_id=uuid4(),
        created_by=user_id,
        source_type="user",
        source_id=user_id,
        ingested_at=now,
        scores={},
        payload_hash=hash_payload(data),
    )
    first = Mock()
    first.scalar_one_or_none.return_value = None if existing else record
    second = Mock()
    second.scalar_one.return_value = record
    session = AsyncMock()
    session.execute.side_effect = [first, second]
    response, outcome = asyncio.run(
        InteractionService(session).createInteraction(
            data,
            "key",
            record.tenant_id,
            record.created_by,
        )
    )
    assert isinstance(response, InteractionRead)
    assert outcome == ("duplicate" if existing else "created")


@pytest.mark.parametrize("commit_fails", [False, True])
def test_ingestion_logged_only_after_commit(monkeypatch, commit_fails):
    import app.api.interaction as endpoint

    response = SimpleNamespace(id=uuid4())
    service = Mock()
    service.createInteraction = AsyncMock(return_value=(response, "created"))
    monkeypatch.setattr(endpoint, "InteractionService", Mock(return_value=service))
    logger = Mock()
    monkeypatch.setattr(endpoint, "logger", logger)
    session = AsyncMock()

    async def commit():
        logger.info.assert_not_called()
        if commit_fails:
            raise RuntimeError("commit failed")

    session.commit.side_effect = commit

    async def check():
        try:
            call = endpoint.create_interaction(
                data=Mock(),
                idempotency_key="key",
                principal=endpoint.IngestionPrincipal(uuid4(), "user", uuid4()),
                session=session,
            )
            if commit_fails:
                with pytest.raises(RuntimeError):
                    await call
                logger.info.assert_not_called()
                session.rollback.assert_awaited_once()
            else:
                assert await call is response
                logger.info.assert_called_once_with(
                    "interaction_ingested", outcome="created"
                )
        finally:
            structlog.contextvars.clear_contextvars()

    asyncio.run(check())
