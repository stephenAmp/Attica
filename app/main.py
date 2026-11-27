from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.logging import configure_logging
from app.api.middleware.request_size import RequestSizeLimitMiddleware
from app.api.middleware.request_logging import RequestLoggingMiddleware
from app.api.ingestion_keys import router as ingestion_keys_router
from app.api.auth import router as auth_router
from app.api.health import router
from app.api.tenant import router as tenant_router
from app.api.interaction import router as interaction_router
from app.api.trace import router as trace_router
from app.api.outcome import router as outcome_router
from app.api.release import router as release_router
from app.core.config import Settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings()
    engine = create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        connect_args={"timeout": 5, "command_timeout": 5},
        hide_parameters=True,
    )
    app.state.session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield
    finally:
        await engine.dispose()


configure_logging()
app = FastAPI(title="Attica", version="0.1.0", lifespan=lifespan)


app.add_middleware(RequestSizeLimitMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(auth_router)
app.include_router(ingestion_keys_router)
app.include_router(tenant_router)
app.include_router(interaction_router)
app.include_router(trace_router)
app.include_router(outcome_router)
app.include_router(release_router)
