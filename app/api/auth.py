from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.schema.auth import LoginResponse, UserLogin
from app.schema.user import UserCreate, UserRead
from app.services.auth import AuthService
from app.storage.postgres import get_session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(
    data: UserCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> UserRead:
    return await AuthService(session).register(data)


@router.post("/login", response_model=LoginResponse)
async def login(
    data: UserLogin,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> LoginResponse:
    return await AuthService(session).login(data)
