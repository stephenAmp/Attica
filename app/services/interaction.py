import uuid as uuid_lib
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.schema.interaction import InteractionCreate, InteractionRead, InteractionEvent
from app.models.general import Interaction, OutboxEvent
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException, status
from sqlalchemy import select
from app.utils.security import hash_payload

class InteractionService:
    def __init__(self, db:AsyncSession):
        self.db = db

    async def createInteraction(self, data:InteractionCreate, idempotency_key: str, tenant_id: UUID, user_id: UUID | None, ingestion_key_id: UUID | None = None) -> tuple[InteractionRead, str]:
        payload_hash = hash_payload(data)
        statement = (
                insert(Interaction)
                .values(
                    tenant_id = tenant_id,
                    idempotency_key = idempotency_key,
                    payload_hash = payload_hash,
                    created_by = user_id,
                    ingestion_key_id = ingestion_key_id,
                    occurred_at = data.occurred_at,
                    status = data.status,
                    model = data.model,
                    latency_ms = data.latency_ms,
                    input_token = data.input_token,
                    output_token = data.output_token,
                    input = data.input,
                    output = data.output,
                    schema_version = data.schema_version,
                    feature = data.feature,
                    environment = data.environment,
                    release =  data.release,
                    prompt_version =  data.prompt_version,
                    trace_id = data.trace_id
                )
                .on_conflict_do_nothing(constraint="uq_tenant_idempotency_key")
                .returning(Interaction)
            )

        interaction = (await self.db.execute(statement)).scalar_one_or_none()
        if interaction is None:
            statement = select(Interaction).where(
                Interaction.tenant_id == tenant_id,
                Interaction.idempotency_key == idempotency_key,
            )

            existing = (await self.db.execute(statement)).scalar_one()

            if existing.payload_hash != payload_hash:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail = "Idempotency key is already used with different payload")
            
            return InteractionRead.model_validate(existing), "duplicate"
        
        
        response = InteractionRead.model_validate(interaction)
        event_id = uuid_lib.uuid4()
        payload = InteractionEvent(
            event_id=event_id,
            interaction_id=interaction.id,
            **response.model_dump(exclude={"id", "created_by", "ingestion_key_id", "source_type", "source_id"}),
        )
        event = OutboxEvent(
            id=event_id,
            interaction_id=interaction.id,
            tenant_id=interaction.tenant_id,
            event_type="interaction created",
            payload=payload.model_dump(mode="json"),
        )
        self.db.add(event)

        return response, "created"
    

            


    async def getInteractionById(self, interaction_id: UUID, tenant_id: UUID )->InteractionRead:
        statement = (
            select(Interaction)
            .where(Interaction.id == interaction_id, Interaction.tenant_id == tenant_id)
        )

        interaction = (await self.db.execute(statement)).scalar_one_or_none()

        if interaction is None:
            raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail="Interaction was not found" )
        
        return InteractionRead.model_validate(interaction)