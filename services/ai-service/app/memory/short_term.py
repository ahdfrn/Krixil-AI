import json
import uuid

from redis.asyncio import Redis

from app.ai.base import ModelMessage
from app.core.config import get_settings


def _key(tenant_id: uuid.UUID, conversation_id: uuid.UUID) -> str:
    return f"krixil:short_term:{tenant_id}:{conversation_id}"


async def get_recent_messages(
    redis: Redis, tenant_id: uuid.UUID, conversation_id: uuid.UUID
) -> list[ModelMessage] | None:
    """Returns the cached recent window, or None on a cache miss — callers fall back to
    Postgres (the durable source of truth) and should repopulate the cache via replace()."""
    # redis-py's stubs type lrange's return as a union covering its (unused here) pipeline mode,
    # which isn't awaitable — mypy can't see that this call site always gets the plain coroutine.
    raw = await redis.lrange(_key(tenant_id, conversation_id), 0, -1)  # type: ignore[misc]
    if not raw:
        return None
    return [ModelMessage(**json.loads(item)) for item in raw]


async def append_message(
    redis: Redis, tenant_id: uuid.UUID, conversation_id: uuid.UUID, role: str, content: str
) -> None:
    settings = get_settings()
    key = _key(tenant_id, conversation_id)
    entry = json.dumps({"role": role, "content": content})
    async with redis.pipeline(transaction=True) as pipe:
        pipe.rpush(key, entry)
        pipe.ltrim(key, -settings.short_term_memory_max_messages, -1)
        pipe.expire(key, settings.short_term_memory_ttl_seconds)
        await pipe.execute()


async def replace(
    redis: Redis, tenant_id: uuid.UUID, conversation_id: uuid.UUID, messages: list[ModelMessage]
) -> None:
    """Repopulates the cache from Postgres after a cache miss."""
    settings = get_settings()
    key = _key(tenant_id, conversation_id)
    window = messages[-settings.short_term_memory_max_messages :]
    entries = [json.dumps({"role": m.role, "content": m.content}) for m in window]
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(key)
        if entries:
            pipe.rpush(key, *entries)
        pipe.expire(key, settings.short_term_memory_ttl_seconds)
        await pipe.execute()
