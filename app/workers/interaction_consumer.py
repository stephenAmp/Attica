import asyncio
import base64
import json
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer, TopicPartition
from pydantic import ValidationError
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.logging import get_logger
from app.schema.interaction import InteractionEvent
from app.workers.process_event import process_event

logger = get_logger()
MAX_ATTEMPTS = 3
DLQ_TOPIC = "interactions.dlq"


async def process_with_retries(session_factory, message, producer):
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            event = InteractionEvent.model_validate_json(message.value)
            bind_contextvars(
                event_id=str(event.event_id),
                tenant_id=str(event.tenant_id),
                interaction_id=str(event.interaction_id),
            )
            async with session_factory() as session:
                processed = await process_event(session, event)
            return "processed" if processed else "duplicate"
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Invalid contracts cannot recover through another processing attempt.
            if attempt < MAX_ATTEMPTS and not isinstance(error, ValidationError):
                logger.warning(
                    "interaction_processing_retry",
                    attempt=attempt,
                    error_type=type(error).__name__,
                )
                await asyncio.sleep(2 ** (attempt - 1))
                continue
            payload = {
                "schema_version": 1,
                "source_topic": message.topic,
                "source_partition": message.partition,
                "source_offset": message.offset,
                "attempts": attempt,
                "error_type": type(error).__name__,
                "failed_at": datetime.now(timezone.utc).isoformat(),
                "key_base64": base64.b64encode(message.key).decode()
                if message.key is not None
                else None,
                "value_base64": base64.b64encode(message.value).decode()
                if message.value is not None
                else None,
            }
            # Preserve arbitrary bytes for replay; never log payloads or error text.
            await producer.send_and_wait(
                DLQ_TOPIC,
                key=f"{message.topic}:{message.partition}:{message.offset}".encode(),
                value=json.dumps(payload).encode(),
            )
            logger.warning(
                "interaction_dead_lettered",
                attempt=attempt,
                error_type=type(error).__name__,
            )
            return "dead_lettered"


async def consume_interactions(session_factory, bootstrap_servers="localhost:9093"):
    consumer = AIOKafkaConsumer(
        "interactions",
        bootstrap_servers=bootstrap_servers,
        group_id="attica-interaction-consumers",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        acks="all",
        enable_idempotence=True,
    )
    try:
        await producer.start()
        await consumer.start()
        async for message in consumer:
            clear_contextvars()
            bind_contextvars(
                topic=message.topic, partition=message.partition, offset=message.offset
            )
            try:
                outcome = await process_with_retries(session_factory, message, producer)
                # Commit failures must replay, not dead-letter successful processing.
                await consumer.commit(
                    {
                        TopicPartition(message.topic, message.partition): message.offset
                        + 1
                    }
                )
                logger.info("interaction_consumed", outcome=outcome)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("interaction_consumer_failed")
                raise
            finally:
                clear_contextvars()
    finally:
        try:
            await consumer.stop()
        finally:
            await producer.stop()
