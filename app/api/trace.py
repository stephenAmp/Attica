from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from app.schema.trace import TraceRead, TraceListResponse
from app.models.general import UserTenants, Role
from app.api.dependencies import get_tenant_membership, required_role_check
from app.storage.postgres import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.trace import TraceService
from pydantic import AwareDatetime
from datetime import datetime, timezone, timedelta
from fastapi import Query


router = APIRouter(prefix="/tenants/{tenant_id}/traces", tags=["traces"])

@router.get("/{trace_id}", response_model = TraceRead)
async def get_trace(
    trace_id: str, 
    membership: Annotated[UserTenants, Depends(get_tenant_membership)], 
    _role: Annotated[Role, Depends(required_role_check({"admin", "developer", "viewer"}))], 
    session: Annotated[AsyncSession, Depends(get_session)]
) -> TraceRead:
    return await TraceService(session).getTrace(tenant_id = membership.tenant_id, trace_id = trace_id)


@router.get("", response_model=TraceListResponse)
async def list_traces(
    membership: Annotated[UserTenants, Depends(get_tenant_membership)],
    _role: Annotated[Role, Depends(required_role_check({"admin", "developer", "viewer"}))],
    session: Annotated[AsyncSession, Depends(get_session)],
    start_time: Annotated[AwareDatetime | None, Query()] = None,
    end_time: Annotated[AwareDatetime | None, Query()] = None,
    release: str | None = None,
    has_error: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TraceListResponse:
    now = datetime.now(timezone.utc)
    resolved_end_time = end_time or now
    resolved_start_time = start_time or (resolved_end_time - timedelta(hours=24))

    if resolved_start_time >= resolved_end_time:
        raise HTTPException(status_code=422, detail="start_time must be before end_time")

    return await TraceService(session).listTraces(tenant_id = membership.tenant_id, start_time = resolved_start_time, end_time = resolved_end_time,release = release, has_error = has_error, limit = limit, offset = offset)