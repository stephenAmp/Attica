from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.general import User
from app.schema.auth import LoginResponse, UserLogin
from app.schema.user import UserCreate, UserRead
from app.utils.security import hash_password, verify_password
from app.utils.token import create_access_token

# Perform password verification even when the email does not exist.
_DUMMY_PASSWORD_HASH = hash_password("not-a-real-account-password")


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def register(self, data: UserCreate) -> UserRead:
        # Argon2 is CPU-intensive; keep it off the async event loop.
        hashed_password = await run_in_threadpool(
            hash_password, data.password.get_secret_value()
        )
        statement = (
            insert(User)
            .values(
                full_name=data.full_name,
                email=str(data.email),
                hashed_password=hashed_password,
            )
            .on_conflict_do_nothing(index_elements=[User.email])
            .returning(User)
        )
        user = (await self.db.execute(statement)).scalar_one_or_none()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email is already registered",
            )

        response = UserRead.model_validate(user)
        return response

    async def login(self, data: UserLogin) -> LoginResponse:
        email = str(data.email).strip().lower()
        user = await self.db.scalar(select(User).where(User.email == email))

        valid_password = await run_in_threadpool(
            verify_password,
            data.password.get_secret_value(),
            user.hashed_password if user is not None else _DUMMY_PASSWORD_HASH,
        )
        if user is None or not valid_password:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is inactive",
            )

        return LoginResponse(
            access_token=create_access_token(subject=str(user.id), is_active=True)
        )
