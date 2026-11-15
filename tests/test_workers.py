import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest
from aiokafka import TopicPartition
from pydantic import ValidationError

from app.schema.interaction import InteractionEvent
from app.workers.process_event import process_event
from app.workers import interaction_consumer as consumer_module
from app.workers import outbox_publisher as publisher_module


def make_event(**changes):
    values = dict(
        event_id=uuid4(), interaction_id=uuid4(), tenant_id=uuid4(),
        schema_version=1, occurred_at=datetime.now(timezone.utc),
        ingested_at=datetime.now(timezone.utc), status="success", scores={},
        model="test", latency_ms=50, input_token=3, output_token=7,
        input="private prompt", output="response",
    )
    return InteractionEvent(**(values | changes))


def session_with_transaction(timeline, *, fail_commit=False):
    session = AsyncMock()

    @asynccontextmanager
    async def transaction():
        try:
            yield
            if fail_commit:
                raise RuntimeError("commit failed")
            timeline.append("db_commit")
        except BaseException:
            timeline.append("db_rollback")
            raise

    session.begin = transaction
    return session


@pytest.mark.parametrize("duplicate", [False, True])
@pytest.mark.parametrize("output,status", [(None, "error"), ("  ", "success"), ("ok", "success")])
def test_summary_and_deduplication(duplicate, output, status):
    timeline = []
    event = make_event(output=output, status=status)
    session = session_with_transaction(timeline)
    session.scalar.return_value = event.interaction_id
    session.execute.return_value = Mock(
        scalar_one_or_none=Mock(return_value=None if duplicate else event.event_id)
    )
    assert asyncio.run(process_event(session, event)) is (not duplicate)
    statement = session.execute.call_args.args[0]
    params = statement.compile().params
    assert params["event_id"] == event.event_id
    assert params["interaction_id"] == event.interaction_id
    assert params["tenant_id"] == event.tenant_id
    assert params["total_tokens"] == 10
    assert params["latency_ms"] == 50
    assert params["is_error"] is (status == "error")
    assert params["output_empty"] is (output is None or not output.strip())
    assert "ON CONFLICT (event_id) DO NOTHING" in str(statement)
    assert "private prompt" not in str(params)
    assert timeline == ["db_commit"]


def test_tenant_mismatch_rolls_back_without_marking_processed():
    timeline = []
    session = session_with_transaction(timeline)
    session.scalar.return_value = None
    with pytest.raises(ValueError):
        asyncio.run(process_event(session, make_event()))
    session.execute.assert_not_awaited()
    assert timeline == ["db_rollback"]


@pytest.mark.parametrize("failure", [None, "commit", "invalid", "offset"])
def test_consumer_commit_order_and_failures(monkeypatch, failure):
    timeline = []
    event = make_event()
    session = session_with_transaction(timeline, fail_commit=failure == "commit")
    session.scalar.return_value = event.interaction_id
    session.execute.return_value = Mock(scalar_one_or_none=Mock(return_value=event.event_id))

    @asynccontextmanager
    async def factory():
        yield session

    message = SimpleNamespace(
        topic="interactions", partition=0, offset=9,
        value=b"invalid" if failure == "invalid" else event.model_dump_json().encode(),
    )
    consumer = AsyncMock()
    consumer.__aiter__.return_value = [message]

    async def commit(offsets):
        assert timeline == ["db_commit"]
        assert offsets == {TopicPartition("interactions", 0): 10}
        if failure == "offset":
            raise RuntimeError("offset commit failed")
        timeline.append("offset_commit")

    consumer.commit.side_effect = commit
    monkeypatch.setattr(consumer_module, "AIOKafkaConsumer", Mock(return_value=consumer))
    logger = Mock()
    monkeypatch.setattr(consumer_module, "logger", logger)
    if failure:
        with pytest.raises((RuntimeError, ValidationError)):
            asyncio.run(consumer_module.consume_interactions(factory))
        logger.exception.assert_called_once()
        if failure != "offset":
            consumer.commit.assert_not_awaited()
    else:
        asyncio.run(consumer_module.consume_interactions(factory))
        assert timeline == ["db_commit", "offset_commit"]
    consumer.stop.assert_awaited_once()


@pytest.mark.parametrize("changes", [{"schema_version": 2}, {"input_token": -1}, {"status": "unknown"}])
def test_contract_rejects_invalid_metrics(changes):
    with pytest.raises(ValidationError):
        make_event(**changes)


@pytest.mark.parametrize("send_fails", [False, True])
def test_publisher_marks_only_after_ack_and_cleans_up(monkeypatch, send_fails):
    timeline = []
    event = SimpleNamespace(tenant_id=uuid4(), payload={}, published_at=None)
    session = session_with_transaction(timeline)
    session.execute.return_value = Mock(scalars=Mock(return_value=Mock(all=Mock(return_value=[event]))))

    @asynccontextmanager
    async def factory():
        yield session

    producer = AsyncMock()

    async def send(**kwargs):
        assert event.published_at is None
        if send_fails:
            raise RuntimeError("broker unavailable")
        timeline.append("kafka_ack")

    producer.send_and_wait.side_effect = send
    monkeypatch.setattr(publisher_module, "AIOKafkaProducer", Mock(return_value=producer))

    async def sleep(seconds):
        assert timeline == (["db_rollback"] if send_fails else ["kafka_ack", "db_commit"])
        assert (event.published_at is None) is send_fails
        raise asyncio.CancelledError()

    monkeypatch.setattr(publisher_module.asyncio, "sleep", sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(publisher_module.publish_outbox(factory))
    producer.stop.assert_awaited_once()
