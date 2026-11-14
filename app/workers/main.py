import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.core.config import Settings
from app.workers.outbox_publisher import publish_outbox


async def main():
    settings = Settings()

    engine = create_async_engine(
        str(settings.database_url),
        pool_pre_ping=True,
        connect_args={"timeout": 5, "command_timeout": 5},
        hide_parameters=True,
    )

    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    try:
        await publish_outbox(
            session_factory=session_factory,
            bootstrap_servers="localhost:9093",
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())