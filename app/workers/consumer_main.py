import asyncio
from app.core.logging import configure_logging

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
)

from app.core.config import Settings
from app.workers.interaction_consumer import consume_interactions


async def main():
    settings = Settings()
    configure_logging()

    engine = create_async_engine(str(settings.database_url), pool_pre_ping=True, hide_parameters=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        await consume_interactions(session_factory=session_factory, bootstrap_servers="localhost:9093")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())