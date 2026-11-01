import time
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.general import User, UserTenants, Role
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


def required_role_check(allowed_roles: set[str]):

    async def dependency(
        membership: Annotated[UserTenants, Depends(get_tenant_membership)],
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> Role:

        role = await session.get(Role, membership.role_id)

        if role is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role not found",
            )

        if role.name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )

        return role

    return dependency


tenant_request_counters = {}
class TenantSpecificRateLimiter:
    def __init__(self, requests_limit: int, time_window: int):
        self.requests_limit = requests_limit
        self.time_window = time_window

    async def __call__(
        self,
        request: Request,
        membership: Annotated[UserTenants, Depends(get_tenant_membership)],
    ):
        tenant_id = membership.tenant_id
        route_path = request.scope["route"].path
        current_time = int(time.time())

        key = f"{tenant_id}:{route_path}"

        if key not in tenant_request_counters:
            tenant_request_counters[key] = {
                "timestamp": current_time,
                "count": 1,
            }
        else:
            counter = tenant_request_counters[key]

            if current_time - counter["timestamp"] >= self.time_window:
                tenant_request_counters[key] = {
                    "timestamp": current_time,
                    "count": 1,
                }

            elif counter["count"] >= self.requests_limit:
                retry_after = max(
                    1,
                    self.time_window - (current_time - counter["timestamp"]),
                )

                raise HTTPException(
                    status_code=429,
                    detail="Too Many Requests",
                    headers={"Retry-After": str(retry_after)},
                )

            else:
                counter["count"] += 1

        # Clean up expired entries
        for k in list(tenant_request_counters.keys()):
            if (
                current_time - tenant_request_counters[k]["timestamp"]
                >= self.time_window
            ):
                tenant_request_counters.pop(k)

        return True

request_counters = {}
class RateLimiter:
    def __init__(self, requests_limit: int, time_window: int):
        self.requests_limit = requests_limit
        self.time_window = time_window
        
    async def __call__(self, request: Request):
        client_ip = request.client.host
        route_path = request.url.path
        current_time = int(time.time())
        key = f"{client_ip}:{route_path}"
        if key not in request_counters:
            request_counters[key] = {"timestamp": current_time, "count": 1}
        else:
            if current_time - request_counters[key]["timestamp"] >= self.time_window:
                request_counters[key] = {"timestamp": current_time, "count": 1}
            elif request_counters[key]["count"] >= self.requests_limit:
                retry_after = max(
                    1,
                    self.time_window - (current_time - request_counters[key]["timestamp"]),
                )
                raise HTTPException(
                    status_code=429, 
                    detail="Too Many Requests", 
                    headers={"Retry-After": str(retry_after)},
                )
            else:
                request_counters[key]["count"] += 1
        # Clean up expired entries
        for k in list(request_counters.keys()):
            if current_time - request_counters[k]["timestamp"] >= self.time_window:
                request_counters.pop(k)
        return True