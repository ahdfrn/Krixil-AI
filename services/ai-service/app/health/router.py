from fastapi import APIRouter, Depends
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.redis import get_redis, redis_health_check
from app.db.session import get_session
from app.schemas.common import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness — no dependency checks, just "is the process up"."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadinessResponse)
async def readiness(
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ReadinessResponse:
    """Readiness — checks the dependencies the app actually needs to serve traffic."""
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    redis_ok = await redis_health_check(redis)

    return ReadinessResponse(
        status="ok" if db_ok and redis_ok else "degraded", database=db_ok, redis=redis_ok
    )
