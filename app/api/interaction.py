from uuid import UUID
from typing import Annotated
from fastapi import APIRouter, Depends, status, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.storage.postgres import get_session
from app.api.dependencies import get_current_user, get_tenant_membership, required_role_check, TenantSpecificRateLimiter
from app.schema.interaction import InteractionRead, InteractionCreate
from app.models.general import User, UserTenants, Role
from app.services.interaction import InteractionService
from fastapi import Path
from app.core.logging import get_logger
from sqlalchemy.exc import SQLAlchemyError

from structlog.contextvars import bind_contextvars


router = APIRouter(prefix="/tenants/{tenant_id}/interactions", tags=["interaction"])

limiter = TenantSpecificRateLimiter(5, 60)

logger = get_logger()

@router.post("", response_model=InteractionRead, dependencies=[Depends(limiter)], status_code=status.HTTP_201_CREATED)
async def create_interaction(
    data: InteractionCreate,
    idempotency_key: Annotated[str, Header(min_length=1, max_length=255)],
    current_user:Annotated[User, Depends(get_current_user)],
    membership: Annotated[UserTenants, Depends(get_tenant_membership)],
    _role: Annotated[Role, Depends(required_role_check({"admin","developer"}))],
    session: Annotated[AsyncSession, Depends(get_session)],
)->InteractionRead:
    try:
        response, outcome = await InteractionService(session).createInteraction(data, idempotency_key, membership.tenant_id, current_user.id)
        await session.commit()

        bind_contextvars(event_id = str(response.id),ingestion_outcome = outcome)
        logger.info("interaction_ingested", outcome = outcome)

        return response
    
    except HTTPException as exc:
        await session.rollback()
        if exc.status_code == 409:
            bind_contextvars(ingestion_outcome="conflict")
            logger.warning("interaction_conflict", outcome="conflict")

        raise

    except SQLAlchemyError:
        await session.rollback()
        bind_contextvars(ingestion_outcome="database_failure")
        
        raise

    except Exception:
        await session.rollback()
        raise

@router.get("/{interaction_id}", dependencies=[Depends(limiter)], response_model=InteractionRead, status_code=200)
async def get_interaction_by_id(
    interaction_id: Annotated[UUID, Path()],
    _current_user: Annotated[User, Depends(get_current_user)],
    membership:Annotated[UserTenants, Depends(get_tenant_membership)],
    _role: Annotated[Role, Depends(required_role_check({"admin", "developer","viewer"}))],
    session: Annotated[AsyncSession, Depends(get_session)]
) ->InteractionRead:
    return await InteractionService(session).getInteractionById(interaction_id, membership.tenant_id)