from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.storage.postgres import get_session
from app.api.dependencies import get_current_user, get_tenant_membership, required_role_check
from app.schema.interaction import InteractionRead, InteractionCreate
from app.models.general import User, UserTenants, Role
from app.services.interaction import InteractionService
from fastapi import Path



router = APIRouter(prefix="/tenants/{tenant_id}/interactions", tags=["interaction"])

@router.post("", response_model=InteractionRead, status_code=status.HTTP_201_CREATED)
async def create_interaction(
    data: InteractionCreate,
    current_user:Annotated[User, Depends(get_current_user)],
    membership: Annotated[UserTenants, Depends(get_tenant_membership)],
    _role: Annotated[Role, Depends(required_role_check({"admin","developer"}))],
    session: Annotated[AsyncSession, Depends(get_session)],
)->InteractionRead:
    return await InteractionService(session).createInteraction(data, membership.tenant_id, current_user.id)

@router.get("/{interaction_id}", response_model=InteractionRead, status_code=200)
async def get_interaction_by_id(
    interaction_id: Annotated[UUID, Path()],
    current_user: Annotated[User, Depends(get_current_user)],
    membership:Annotated[UserTenants, Depends(get_tenant_membership)],
    _role: Annotated[Role, Depends(required_role_check({"admin", "developer","viewer"}))],
    session: Annotated[AsyncSession, Depends(get_session)]
) ->InteractionRead:
    return await InteractionService(session).getInteractionById(interaction_id, membership.tenant_id)