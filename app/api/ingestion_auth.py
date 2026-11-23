from dataclasses import dataclass
from typing import Annotated, Literal
from uuid import UUID
from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.general import IngestionAPIKey
from app.storage.postgres import get_session
from app.utils.api_key import parse_api_key, verify_api_key
from app.api.dependencies import (
    TenantSpecificRateLimiter, bearer_scheme, get_current_user,
    get_tenant_membership, required_role_check,
)
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from structlog.contextvars import bind_contextvars

write_role = required_role_check({"admin", "developer"})

limiter = TenantSpecificRateLimiter(1000, 60)
@dataclass(frozen=True)
class IngestionPrincipal:
    tenant_id: UUID
    source_type: Literal["user", "api_key"]
    source_id: UUID


async def get_ingestion_principal(
    tenant_id: UUID,
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    api_key: Annotated[str | None, Header(alias="X-Attica-API-Key")] = None,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
) -> IngestionPrincipal:


    if api_key is not None and credentials is not None:
        raise HTTPException(400, "Provide only one credential")

    if api_key is not None:
        parsed = parse_api_key(api_key)

        if parsed is None:
            raise HTTPException(401, "Invalid API key")

        key_id, secret = parsed
        record = await session.get(IngestionAPIKey, key_id)

        if (
            record is None
            or record.revoked_at is not None
            or not verify_api_key(secret, record.secret_hash)
        ):
            raise HTTPException(401, "Invalid API key")

        if record.tenant_id != tenant_id:
            raise HTTPException(403, "API key cannot access this tenant")

        bind_contextvars(tenant_id=str(record.tenant_id), ingestion_key_id=str(record.id))
        principal = IngestionPrincipal(record.tenant_id, "api_key", record.id)
    else:
        user = await get_current_user(credentials, session)
        membership = await get_tenant_membership(tenant_id, user, session)
        await write_role(membership, session)
        principal = IngestionPrincipal(membership.tenant_id, "user", user.id)

    limiter.check(request, principal.tenant_id)
    return principal
