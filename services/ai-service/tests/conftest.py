import os

# Must be set before `from app.main import app` below — Settings() reads .env at import time, and
# a real local .env (e.g. a real TAVILY_API_KEY, added for live dev use) must never leak into the
# offline suite: Settings(env_file=".env") only falls back to the file for anything not already in
# os.environ, so setting these here first makes the suite hermetic regardless of what a developer's
# own .env happens to contain. Caught for real: test_tools.py's "no key configured" test started
# making genuine network calls to api.tavily.com once a real key existed in .env.
os.environ.setdefault("OTEL_ENABLED", "false")
os.environ.setdefault("TAVILY_API_KEY", "")
os.environ.setdefault("MODEL_PROVIDER", "mock")
os.environ.setdefault("MODEL_FALLBACK_PROVIDERS", "")
os.environ.setdefault("HOST_RUNNER_API_KEY", "test-only-host-key")

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.models  # noqa: F401  # populate Base.metadata before create_all
from app.db.base import Base
from app.db.redis import get_redis
from app.db.session import get_session
from app.main import app
from app.storage.dependency import get_storage
from tests.fakes import FakeObjectStorage


@pytest.fixture
async def engine(tmp_path):
    # A temp *file* database, not `:memory:` + StaticPool. StaticPool hands every session the
    # exact same physical connection, which is fine as long as only one session is ever open at a
    # time — but app/memory/long_term.py's background task opens a second, independent session
    # mid-request (see app/chat/router.py), and on a single shared SQLite connection that second
    # session's rollback (e.g. MockProvider's non-JSON response failing to parse) rolled back the
    # *first* session's still-uncommitted work too — a real bug this test suite caught, traced to
    # FastAPI not guaranteeing BackgroundTasks run after a yield-dependency's own commit. A file-
    # backed database lets each session open its own real connection with proper transaction
    # isolation, matching how separate Postgres connections behave in production (where this was
    # never actually a risk) — StaticPool's single-connection sharing was the test-only artifact.
    db_path = tmp_path / "test.db"
    test_engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_path}", connect_args={"check_same_thread": False}
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
    # extract_and_store_memories (app/memory/long_term.py) is a background task that also opens
    # its own session directly, entirely detached from any request's Depends(get_session) — same
    # reason it needs its own patch target here too.
    monkeypatch.setattr("app.memory.long_term.AsyncSessionLocal", session_factory)
    # _run_agent_in_background (app/agents/router.py) runs the whole agent loop off the request
    # entirely now, on its own session — same reason as the two patches above.
    monkeypatch.setattr("app.agents.router.AsyncSessionLocal", session_factory)
    # run_swarm_in_background (app/agents/swarm.py) — same reason again: its own detached
    # sessions (one for decomposition/child creation, one per concurrent child, one for
    # synthesis) all need to land on the test engine, not the real Postgres AsyncSessionLocal
    # defaults to.
    monkeypatch.setattr("app.agents.swarm.AsyncSessionLocal", session_factory)
    # run_brain_index_in_background (app/brain/service.py) — same reason again.
    monkeypatch.setattr("app.brain.service.AsyncSessionLocal", session_factory)
    # run_hermes_agent_in_background/resume_hermes_agent_in_background (app/agents/
    # hermes_runtime.py) — same reason again: their own detached sessions, one per SSE event.
    monkeypatch.setattr("app.agents.hermes_runtime.AsyncSessionLocal", session_factory)

    yield

    app.dependency_overrides.clear()
    await fake_redis.aclose()


@pytest.fixture
async def client(override_dependencies):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
