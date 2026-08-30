import time

from fastapi import Depends, HTTPException, status
from redis.asyncio import Redis

from app.core.config import get_settings
from app.db.redis import get_redis
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context


async def enforce_chat_rate_limit(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    redis: Redis = Depends(get_redis),
) -> None:
    """Fixed-window limiter, per tenant, shared across /chat and /chat/stream. Fixed windows can
    let a burst of up to 2x the limit through right at a window boundary — acceptable for Phase 1
    (protecting against runaway/misbehaving clients, not precise quota enforcement); a sliding
    window is a straightforward upgrade later if that matters."""
    settings = get_settings()
    window = int(time.time() // 60)
    key = f"krixil:ratelimit:chat:{tenant_ctx.tenant_id}:{window}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)

    if count > settings.rate_limit_chat_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded — try again in a moment",
        )
