from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    pool_pre_ping=True,  # drop dead connections instead of failing a request
)

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request, closed afterwards.

    Services decide when to commit; nothing is committed implicitly.
    """
    async with SessionLocal() as session:
        yield session
