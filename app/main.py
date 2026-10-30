from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.auth import router as auth_router
from app.api.health import router
from app.api.tenant import router as tenant_router
from app.core.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    engine = create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        connect_args={"timeout": 5, "command_timeout": 5},
    )
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(title="Attica", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(auth_router)

app.include_router(tenant_router)
