import asyncio

from aiokafka import AIOKafkaConsumer, TopicPartition
from structlog.contextvars import bind_contextvars, clear_contextvars

from app.core.logging import get_logger
from app.schema.interaction import InteractionEvent
from app.workers.process_event import process_event

logger = get_logger()


async def consume_interactions(session_factory, bootstrap_servers="localhost:9093"):
    consumer = AIOKafkaConsumer(
        "interactions",
        bootstrap_servers=bootstrap_servers,
        group_id="attica-interaction-consumers",
        enable_auto_commit=False,
        auto_offset_reset="earliest",
    )
    try:
        await consumer.start()
        async for message in consumer:
            clear_contextvars()
            bind_contextvars(topic=message.topic, partition=message.partition, offset=message.offset)
            try:
                event = InteractionEvent.model_validate_json(message.value)
                bind_contextvars(event_id=str(event.event_id), tenant_id=str(event.tenant_id), interaction_id=str(event.interaction_id))
                async with session_factory() as session:
                    processed = await process_event(session, event)
                # Store the next offset only after the database transaction commits.
                await consumer.commit({TopicPartition(message.topic, message.partition): message.offset + 1})
                logger.info("interaction_processed", outcome="processed" if processed else "duplicate")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("interaction_processing_failed")
                # No offset advance: restart retries this event. DLQ is a later step.
                raise
            finally:
                clear_contextvars()
    finally:
        await consumer.stop()
