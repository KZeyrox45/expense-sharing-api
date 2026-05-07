# Manage async database engine and session factory

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
)

from app.core.config import settings

# Engine is connection pool - create once, use whole app lifetime
# echo=True prints SQL queries in development (suitable for debug)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=not settings.is_production     # Turn echo off in production
    # pool_size and max_overflow is important when scaling,
    # leave them at their default values (5 and 10) for development
)

# Session factory - create a new session for each request.
# expire_on_commit=False: keep objects accessible after commit
# (important when to return data after committing in async context).
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency - inject AsyncSession into route handlers.

    Use pattern:
        async def my_route(db: AsyncSession = Depends(get_db)):
            ...

    Session will close itself when request ends (even if there's some exceptions)
    """

    async with AsyncSessionLocal() as session:
        try:
            yield session
            # No auto-commit here - server layer will decide when to commit.
        except Exception:
            await session.rollback()
            raise