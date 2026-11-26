from sqlalchemy.ext.asyncio import AsyncSession
from app.schema.interaction_batch import InteractionBatchCreate, BatchItemResult, InteractionBatchRead
from app.api.ingestion_auth import IngestionPrincipal
from app.services.interaction import InteractionService
from fastapi import HTTPException

class InteractionBatchService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.interaction_service = InteractionService(db)


    async def createBatch(self, data: InteractionBatchCreate, principal: IngestionPrincipal) -> InteractionBatchRead:
        results = []
        for index, item in enumerate(data.items):
            try:
              interaction, outcome = await self.interaction_service.createInteraction(
                item.interaction,
                item.idempotency_key,
                tenant_id=principal.tenant_id,
                user_id=principal.source_id if principal.source_type == "user" else None,
                ingestion_key_id=principal.source_id if principal.source_type == "api_key" else None,
                )

            except HTTPException as exc:
                if exc.status_code == 409:
                    raise HTTPException(status_code = 409, detail = {"index":index, "message":"Idempotency key already exists with different content"}) from exc

                raise

            results.append(BatchItemResult(index = index, interaction_id = interaction.id, status = "created" if outcome == "created" else "duplicate"))

        return InteractionBatchRead(result=results)
