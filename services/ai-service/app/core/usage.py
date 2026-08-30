import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_record import UsageRecord


async def record_usage(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    model: str,
    usage: dict,
) -> None:
    session.add(
        UsageRecord(
            tenant_id=tenant_id,
            user_id=user_id,
            conversation_id=conversation_id,
            model=model,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
        )
    )
