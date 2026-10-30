import asyncio

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.models.general import Role


async def seed_roles():
    engine = create_async_engine(str(Settings().database_url))
    session_factory = async_sessionmaker(engine)

    try:
        async with session_factory.begin() as session:
            statement = (
                insert(Role)
                .values([
                    {"name": "admin"},
                    {"name": "viewer"},
                    {"name": "developer"},
                ])
                .on_conflict_do_nothing(index_elements=[Role.name])
            )
            await session.execute(statement)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed_roles())