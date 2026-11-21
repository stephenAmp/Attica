from fastapi import APIRouter, Depends
from typing import Annotated
from app.schema.outcome import OutcomeRead, OutcomeCreate
from sqlalchemy.ext.asyncio import AsyncSession
from app.storage.postgres import get_session
from app.api.dependencies import get_tenant_membership, required_role_check
from app.models.general import UserTenants, Tenant
from app.services.outcome import OutcomeService

router = APIRouter(prefix = "/tenants/{tenant_id}/outcomes", tags = ["outcome"])

@router.post("/", response_model = OutcomeRead)
async def create_outcome(
    data: OutcomeCreate,
    membership: Annotated[Tenant, Depends(get_tenant_membership)],
    _role: Annotated[UserTenants, Depends(required_role_check({"developer", "admin"}))],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    try:
        outcome = await OutcomeService.createOutcome(tenant_id = membership.tenant_id, data = data)
        response = OutcomeRead.model_validate(outcome, from_attributes = True)
        await session.commit()
        return response

    except Exception:
        await session.rollback()
        raise