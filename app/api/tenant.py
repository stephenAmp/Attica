from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, get_tenant_membership
from app.models.general import User, UserTenants
from app.schema.tenant import TenantCreate, TenantRead
from app.services.tenant import TenantService
from app.storage.postgres import get_session

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantRead, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    data: TenantCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantRead:
    try:
        response =  await TenantService(session).createTenant(data, creator_id=current_user.id)
        await session.commit()
        return response

    except Exception:
        await session.rollback()
        raise


@router.get("/{tenant_id}", response_model=TenantRead)
async def get_tenant(
    membership: Annotated[UserTenants, Depends(get_tenant_membership)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantRead:
    return await TenantService(session).getTenant(membership.tenant_id)
