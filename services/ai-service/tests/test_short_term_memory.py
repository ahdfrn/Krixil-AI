import uuid

import fakeredis.aioredis
import pytest

from app.ai.base import ModelMessage
from app.core.config import get_settings
from app.memory import short_term


@pytest.fixture
async def redis():
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield client
    await client.aclose()


async def test_get_recent_messages_is_none_on_cache_miss(redis):
    result = await short_term.get_recent_messages(redis, uuid.uuid4(), uuid.uuid4())
    assert result is None


async def test_append_then_get_returns_messages_in_order(redis):
    tenant_id, conversation_id = uuid.uuid4(), uuid.uuid4()

    await short_term.append_message(redis, tenant_id, conversation_id, "user", "hello")
    await short_term.append_message(redis, tenant_id, conversation_id, "assistant", "hi there")

    result = await short_term.get_recent_messages(redis, tenant_id, conversation_id)
    assert result == [
        ModelMessage(role="user", content="hello"),
        ModelMessage(role="assistant", content="hi there"),
    ]


async def test_append_trims_to_configured_window(redis, monkeypatch):
    monkeypatch.setattr(get_settings(), "short_term_memory_max_messages", 3)
    tenant_id, conversation_id = uuid.uuid4(), uuid.uuid4()

    for i in range(5):
        await short_term.append_message(redis, tenant_id, conversation_id, "user", f"message {i}")

    result = await short_term.get_recent_messages(redis, tenant_id, conversation_id)
    assert [m.content for m in result] == ["message 2", "message 3", "message 4"]


async def test_append_sets_expiry(redis):
    tenant_id, conversation_id = uuid.uuid4(), uuid.uuid4()
    await short_term.append_message(redis, tenant_id, conversation_id, "user", "hello")

    ttl = await redis.ttl(short_term._key(tenant_id, conversation_id))
    assert ttl > 0


async def test_replace_overwrites_existing_cache(redis):
    tenant_id, conversation_id = uuid.uuid4(), uuid.uuid4()
    await short_term.append_message(redis, tenant_id, conversation_id, "user", "stale")

    await short_term.replace(
        redis, tenant_id, conversation_id, [ModelMessage(role="user", content="fresh")]
    )

    result = await short_term.get_recent_messages(redis, tenant_id, conversation_id)
    assert result == [ModelMessage(role="user", content="fresh")]


async def test_replace_with_empty_list_clears_cache(redis):
    tenant_id, conversation_id = uuid.uuid4(), uuid.uuid4()
    await short_term.append_message(redis, tenant_id, conversation_id, "user", "stale")

    await short_term.replace(redis, tenant_id, conversation_id, [])

    result = await short_term.get_recent_messages(redis, tenant_id, conversation_id)
    assert result is None
