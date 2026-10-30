from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.models.general import User
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
    return await TenantService(session).createTenant(data, creator_id=current_user.id)
