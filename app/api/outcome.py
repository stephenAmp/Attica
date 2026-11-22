from fastapi import APIRouter, Depends
from typing import Annotated
from app.schema.outcome import OutcomeRead, OutcomeCreate
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.ingestion_auth import IngestionPrincipal, get_ingestion_principal
from app.storage.postgres import get_session
from app.services.outcome import OutcomeService

router = APIRouter(prefix = "/tenants/{tenant_id}/outcomes", tags = ["outcome"])

@router.post("", response_model = OutcomeRead)
async def create_outcome(
    data: OutcomeCreate,
    principal: Annotated[IngestionPrincipal, Depends(get_ingestion_principal)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    try:
        outcome = await OutcomeService(session).createOutcome(tenant_id = principal.tenant_id, data = data)
        response = OutcomeRead.model_validate(outcome, from_attributes = True)
        await session.commit()
        return response

    except Exception:
        await session.rollback()
        raise