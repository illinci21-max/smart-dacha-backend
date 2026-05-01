"""
Pytest конфігурація та shared fixtures.
ВИПРАВЛЕНО: додано other_user та expired_premium_user fixtures для IDOR тестів.
"""
import asyncio
import os
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.user import User
from passlib.context import CryptContext

# Для тестів можна задати через env або .env.test
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://smartdacha:secret@localhost:5432/smartdacha_test")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    TestSessionLocal = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        yield client

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"test_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=pwd_context.hash("password123"),
        subscription_tier="free",
        plots_limit=1,
        plants_limit=10,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def other_user(db_session: AsyncSession) -> User:
    """Другий user для тестів IDOR."""
    user = User(
        id=uuid.uuid4(),
        email=f"other_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=pwd_context.hash("password123"),
        subscription_tier="free",
        plots_limit=1,
        plants_limit=10,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def premium_user(db_session: AsyncSession) -> User:
    from datetime import datetime, timezone, timedelta
    user = User(
        id=uuid.uuid4(),
        email=f"premium_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=pwd_context.hash("password123"),
        subscription_tier="premium",
        subscription_expires_at=datetime.now(timezone.utc) + timedelta(days=365),
        plots_limit=999,
        plants_limit=9999,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def expired_premium_user(db_session: AsyncSession) -> User:
    """User з прострочeною підпискою — FIX S-13."""
    from datetime import datetime, timezone, timedelta
    user = User(
        id=uuid.uuid4(),
        email=f"expired_{uuid.uuid4().hex[:8]}@example.com",
        password_hash=pwd_context.hash("password123"),
        subscription_tier="premium",
        # Прострочено вчора
        subscription_expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        plots_limit=999,
        plants_limit=9999,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient, test_user: User) -> dict:
    resp = await client.post("/api/v1/auth/login", json={
        "email": test_user.email,
        "password": "password123",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def other_user_auth_headers(client: AsyncClient, other_user: User) -> dict:
    resp = await client.post("/api/v1/auth/login", json={
        "email": other_user.email,
        "password": "password123",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def premium_auth_headers(client: AsyncClient, premium_user: User) -> dict:
    resp = await client.post("/api/v1/auth/login", json={
        "email": premium_user.email,
        "password": "password123",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def expired_premium_auth_headers(client: AsyncClient, expired_premium_user: User) -> dict:
    resp = await client.post("/api/v1/auth/login", json={
        "email": expired_premium_user.email,
        "password": "password123",
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
