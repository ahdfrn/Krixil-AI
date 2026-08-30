import os

# Must be set before `from app.main import app` below — tracing is configured at import time.
# No collector is running in the offline suite; leaving it on just adds a background export
# thread that logs harmless-but-noisy connection errors as the test process exits.
os.environ.setdefault("OTEL_ENABLED", "false")

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  # populate Base.metadata before create_all
from app.db.base import Base
from app.db.redis import get_redis
from app.db.session import get_session
from app.main import app
from app.storage.dependency import get_storage
from tests.fakes import FakeObjectStorage

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def engine():
    test_engine = create_async_engine(
        TEST_DATABASE_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
def session_factory(engine):
    return async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)


@pytest.fixture(autouse=True)
async def override_dependencies(session_factory, monkeypatch):
    async def _get_session_override():
        async with session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    fake_redis = fakeredis.aioredis.FakeRedis(decode_responses=True)

    async def _get_redis_override():
        yield fake_redis

    app.dependency_overrides[get_session] = _get_session_override
    app.dependency_overrides[get_redis] = _get_redis_override
    app.dependency_overrides[get_storage] = lambda: FakeObjectStorage()
    # chat_stream opens its own session directly (see app/chat/router.py) rather than via
    # Depends(get_session), so it needs its own patch target to land on the test engine too.
    monkeypatch.setattr("app.chat.router.AsyncSessionLocal", session_factory)

    yield

    app.dependency_overrides.clear()
    await fake_redis.aclose()


@pytest.fixture
async def client(override_dependencies):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
