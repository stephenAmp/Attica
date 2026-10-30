import uuid as UUID
from sqlalchemy.ext.asyncio import AsyncSession
from app.schema.interaction import InteractionCreate, InteractionRead
from app.models.general import Interaction
from sqlalchemy.dialects.postgresql import insert
from fastapi import HTTPException, status
from sqlalchemy import select


class InteractionService:
    def __init__(self, db:AsyncSession):
        self.db = db

    async def createInteraction(self, data:InteractionCreate, tenant_id: str, user_id: str) -> InteractionRead:
        try:
            statement = (
                insert(Interaction)
                .values(
                    tenant_id = tenant_id,
                    created_by = user_id,
                    occurred_at = data.occurred_at,
                    status = data.status,
                    model = data.model,
                    latency_ms = data.latency_ms,
                    input_token = data.input_token,
                    output_token = data.output_token,
                    input = data.input,
                    output = data.output,
                    schema_version = data.schema_version   
                )
                .returning(Interaction)
            )

            interaction = (await self.db.execute(statement)).scalar_one()
            response = InteractionRead.model_validate(interaction)
            await self.db.commit()
            return response
            

        except Exception:
            await self.db.rollback()
            raise

    async def getInteractionById(self, interaction_id: UUID, tenant_id: UUID )->InteractionRead:
        statement = (
            select(Interaction)
            .where(Interaction.id == interaction_id, Interaction.tenant_id == tenant_id)
        )

        interaction = (await self.db.execute(statement)).scalar_one_or_none()

        if interaction is None:
            raise HTTPException(status_code = status.HTTP_404_NOT_FOUND, detail="Interaction was not found" )
        
        return InteractionRead.model_validate(interaction)