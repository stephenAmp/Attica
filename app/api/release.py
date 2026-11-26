from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import AwareDatetime
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.dependencies import get_tenant_membership, required_role_check
from app.models.general import UserTenants, Role
from app.schema.release import ReleaseComparisonRead
from app.services.release import ReleaseService
from app.storage.postgres import get_session

router = APIRouter(prefix="/tenants/{tenant_id}/releases", tags=["releases"])

@router.get("/compare", response_model=ReleaseComparisonRead)
async def compare_releases(
    baseline_release: Annotated[str, Query(min_length=1)],
    candidate_release: Annotated[str, Query(min_length=1)],
    feature: Annotated[str, Query(min_length=1)],
    environment: Annotated[str, Query(min_length=1)],
    start_time: Annotated[AwareDatetime, Query()],
    end_time: Annotated[AwareDatetime, Query()],
    membership: Annotated[UserTenants, Depends(get_tenant_membership)],
    _role: Annotated[Role,Depends(required_role_check({"admin", "developer", "viewer"}))],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReleaseComparisonRead:

    if baseline_release == candidate_release:
        raise HTTPException(status_code = 422, detail="Baseline and candidate releases must differ")

    if start_time >= end_time:
        raise HTTPException(status_code = 422, detail="start time must be before end time")

    return await ReleaseService(session).compareReleases(
        tenant_id = membership.tenant_id,
        baseline_release = baseline_release,
        candidate_release = candidate_release,
        feature = feature,
        environment = environment,
        start_time = start_time,
        end_time = end_time
    )