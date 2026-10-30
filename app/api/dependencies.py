from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.general import User, UserTenants
from app.storage.postgres import get_session
from app.utils.token import decode_token

# Login accepts JSON; Swagger accepts the returned bearer token directly.
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing access token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_token(credentials.credentials)
        user_id = UUID(payload["sub"])
    except (PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise unauthorized from exc

    # Read the account now so deleted or deactivated users cannot use old tokens.
    user = await session.get(User, user_id)
    if user is None:
        raise unauthorized
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account is inactive"
        )
    return user


async def get_tenant_membership(
    tenant_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserTenants:
    membership = await session.get(
        UserTenants, {"user_id": current_user.id, "tenant_id": tenant_id}
    )
    if membership is None:
        # Use the same response for nonexistent and inaccessible tenants.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found"
        )
    return membership
