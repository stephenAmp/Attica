from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schema.auth import LoginResponse, UserLogin
from app.schema.user import UserCreate, UserRead
from app.services.auth import AuthService
from app.storage.postgres import get_session
from app.api.dependencies import RateLimiter

router = APIRouter(prefix="/auth", tags=["auth"])
limiter = RateLimiter(100, 60)

@router.post("/register",  response_model=UserRead, dependencies=[Depends(limiter)], status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRead:
    async with session.begin():
        return await AuthService(session).register(data)


@router.post("/login", dependencies=[Depends(limiter)], response_model=LoginResponse)
async def login(
    data: UserLogin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    return await AuthService(session).login(data)
