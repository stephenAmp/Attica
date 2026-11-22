from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_tenant_membership, required_role_check
from app.models.general import UserTenants
from app.schema.ingestion_api_key import APIKeyCreate, APIKeyIssued, APIKeyRead
from app.services.ingestion_api_key import IngestionAPIKeyService
from app.storage.postgres import get_session

router = APIRouter(
    prefix="/tenants/{tenant_id}/ingestion-keys",
    tags=["ingestion-keys"],
    dependencies=[Depends(required_role_check({"admin"}))],
)
Membership = Annotated[UserTenants, Depends(get_tenant_membership)]
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=APIKeyIssued, status_code=201)
async def issue_key(data: APIKeyCreate, response: Response, membership: Membership, session: Session):
    response.headers["Cache-Control"] = "no-store"
    return await IngestionAPIKeyService(session).createIngestionKey(
        data, membership.tenant_id, membership.user_id
    )


@router.get("", response_model=list[APIKeyRead])
async def list_keys(membership: Membership, session: Session):
    return await IngestionAPIKeyService(session).listIngestionKeys(membership.tenant_id)


@router.delete("/{key_id}", status_code=204)
async def revoke_key(key_id: UUID, membership: Membership, session: Session):
    await IngestionAPIKeyService(session).revokeIngestionKey(key_id, membership.tenant_id)
