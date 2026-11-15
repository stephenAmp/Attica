from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.general import Interaction, ProcessedEvent
from app.schema.interaction import InteractionEvent


async def process_event(session: AsyncSession, event: InteractionEvent) -> bool:
    """Atomically persist a derived summary; False means already processed."""
    
    async with session.begin():
        interaction_id = await session.scalar(
            select(Interaction.id).where(
                Interaction.id == event.interaction_id,
                Interaction.tenant_id == event.tenant_id,
            )
        )
        if interaction_id is None:
            raise ValueError("Interaction does not belong to the event tenant")

        result = await session.execute(
            insert(ProcessedEvent)
            .values(
                event_id=event.event_id,
                interaction_id=event.interaction_id,
                tenant_id=event.tenant_id,
                total_tokens=event.input_token + event.output_token,
                latency_ms=event.latency_ms,
                is_error=event.status == "error",
                output_empty=not (event.output or "").strip(),
            )
            .on_conflict_do_nothing(index_elements=[ProcessedEvent.event_id])
            .returning(ProcessedEvent.event_id)
        )
        return result.scalar_one_or_none() is not None
