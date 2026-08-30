from collections.abc import AsyncGenerator

from redis.asyncio import Redis

from app.core.config import get_settings

settings = get_settings()

_redis_client: Redis = Redis.from_url(settings.redis_url, decode_responses=True)


async def get_redis() -> AsyncGenerator[Redis, None]:
    yield _redis_client


async def redis_health_check(client: Redis) -> bool:
    try:
        return await client.ping()
    except Exception:
        return False
