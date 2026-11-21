from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends
from app.schema.trace import TraceRead
from app.models.general import UserTenants, Role
from app.api.dependencies import get_tenant_membership, required_role_check
from app.storage.postgres import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.trace import TraceService

router = APIRouter(prefix="/tenants/{tenant_id}/traces", tags=["traces"])

@router.get("/{trace_id}", response_model = TraceRead)
async def get_trace(
    trace_id: str, 
    membership: Annotated[UserTenants, Depends(get_tenant_membership)], 
    _role: Annotated[Role, Depends(required_role_check({"admin", "developer", "viewer"}))], 
    session: Annotated[AsyncSession, Depends(get_session)]
) -> TraceRead:
    return await TraceService(session).getTrace(tenant_id = membership.tenant_id, trace_id = trace_id)