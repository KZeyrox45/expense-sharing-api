import asyncio
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models.group import Group, GroupMember, MemberRole
from app.db.models.user import User
from app.db.session import get_db
from app.main import app

# --- Test database engine -------------------------------------------------------
# Uses the same DATABASE_URL but a separate test schema via a different DB name.
# NullPool: each connection is created fresh and closed immediately,
# preventing "another operation is in progress" errors caused by
# connection pool reuse across different asyncio event loops.
_test_db_name = settings.DATABASE_URL.split("/")[-1]
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    f"/{_test_db_name}", "/expense_sharing_test"
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# --- Table setup - sync fixture avoids session-scoped async loop conflict ---------
@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """
    Create all tables once before the test session, drop after.

    Using a SYNC fixture + asyncio.run() intentionally.
    A session-scoped ASYNC fixture requires a session-scoped event loop,
    which conflicts with function-scoped test loops in pytest-asyncio >= 0.23.
    asyncio.run() creates its own loop just for setup/teardown, avoiding the conflict.
    """
    async def _create():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)   # clean slate
            await conn.run_sync(Base.metadata.create_all)

    async def _drop():
        async with test_engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    asyncio.run(_create())
    yield
    asyncio.run(_drop())


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an AsyncSession that rolls back all changes after each test.

    Pattern: open connection -> begin transaction -> yield session -> rollback.
    This is the "join external transaction" pattern from SQLAlchemy 2.0 docs.
    Each test runs in isolation without truncating tables.
    """
    # connect() returns AsyncConnection, which is valid as AsyncSession bind
    conn = await test_engine.connect()
    await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    try:
        yield session
    finally:
        await session.close()
        await conn.rollback()
        await conn.close()


# --- HTTP test client ----------------------------------------------------------
@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    AsyncClient with the test DB session injected via dependency override.
    Routes use the rollback-isolated session - no data persists between tests.
    """
    async def override_get_db():
        yield db
    
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test"
    ) as ac:
        yield ac
    # Always clear overrides even if test fails
    app.dependency_overrides.clear()


# --- User fixtures --------------------------------------------------------------
@pytest_asyncio.fixture
async def user_alice(db: AsyncSession) -> User:
    user = User(
        email="alice@test.com",
        username="alice",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def user_bob(db: AsyncSession) -> User:
    user = User(
        email="bob@test.com",
        username="bob",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def user_charlie(db: AsyncSession) -> User:
    user = User(
        email="charlie@test.com",
        username="charlie",
        hashed_password=hash_password("password123"),
    )
    db.add(user)
    await db.flush()
    return user


def auth_headers(user: User) -> dict[str, str]:
    """Generate Bearer token header for a given user. Used in all test HTTP calls."""
    token = create_access_token(user.id)
    return {"Authorization": f"Bearer {token}"}


# --- Group fixtures -------------------------------------------------------------
@pytest_asyncio.fixture
async def group_with_alice_and_bob(
    db: AsyncSession,
    user_alice: User,
    user_bob: User,
) -> Group:
    """A group where alice is admin and bob is member."""
    group = Group(name="Test Group", created_by=user_alice.id)
    db.add(group)
    await db.flush()

    db.add(GroupMember(group_id=group.id, user_id=user_alice.id, role=MemberRole.admin))
    db.add(GroupMember(group_id=group.id, user_id=user_bob.id, role=MemberRole.member))
    await db.flush()
    return group