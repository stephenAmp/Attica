import asyncio
import json
from datetime import datetime, timezone
from aiokafka import AIOKafkaProducer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
from app.models.general import OutboxEvent
from app.core.logging import get_logger

logger = get_logger()

async def publish_outbox(
    session_factory: async_sessionmaker[AsyncSession],
    bootstrap_servers: str = "localhost:9093",
):
    producer = AIOKafkaProducer(
        bootstrap_servers=bootstrap_servers,
        acks="all",
        enable_idempotence=True,
    )


    try:
        await producer.start()

        while True:
            try:
                async with session_factory() as session:
                    async with session.begin():
                        statement = (
                            select(OutboxEvent)
                            .where(OutboxEvent.published_at.is_(None))
                            .order_by(OutboxEvent.created_at)
                            .limit(100)
                            .with_for_update(skip_locked=True)
                        )

                        result = await session.execute(statement)
                        events = result.scalars().all()

                        for event in events:
                            await producer.send_and_wait(
                                topic="interactions",
                                key=str(event.tenant_id).encode(),
                                value=json.dumps(event.payload).encode(),
                            )
                            event.published_at = datetime.now(timezone.utc)

                await asyncio.sleep(5)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Outbox publishing failed. Retrying in 5 seconds.")
                await asyncio.sleep(5)

    finally:
        await producer.stop()