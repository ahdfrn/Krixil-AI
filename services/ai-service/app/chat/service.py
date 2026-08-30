import uuid

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelMessage
from app.memory import short_term
from app.models.conversation import Conversation
from app.models.message import Message
from app.tenancy.context import TenantContext


async def get_or_create_conversation(
    session: AsyncSession, tenant_ctx: TenantContext, conversation_id: uuid.UUID | None
) -> Conversation:
    if conversation_id is None:
        conversation = Conversation(tenant_id=tenant_ctx.tenant_id, user_id=tenant_ctx.user_id)
        session.add(conversation)
        await session.flush()
        return conversation

    conversation = await get_conversation_or_404(session, tenant_ctx, conversation_id)
    return conversation


async def get_conversation_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, conversation_id: uuid.UUID
) -> Conversation:
    # tenant_id is always part of the WHERE clause — a conversation belonging to another
    # tenant returns 404 exactly like a non-existent one, never a 403 that would confirm it exists.
    conversation = (
        await session.execute(
            select(Conversation).where(
                Conversation.id == conversation_id, Conversation.tenant_id == tenant_ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


async def list_conversations(session: AsyncSession, tenant_ctx: TenantContext) -> list[Conversation]:
    result = await session.execute(
        select(Conversation)
        .where(Conversation.tenant_id == tenant_ctx.tenant_id, Conversation.user_id == tenant_ctx.user_id)
        .order_by(Conversation.created_at.desc())
    )
    return list(result.scalars().all())


async def list_messages(
    session: AsyncSession, tenant_ctx: TenantContext, conversation_id: uuid.UUID
) -> list[Message]:
    result = await session.execute(
        select(Message)
        .where(Message.tenant_id == tenant_ctx.tenant_id, Message.conversation_id == conversation_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def save_message(
    session: AsyncSession, tenant_ctx: TenantContext, conversation_id: uuid.UUID, role: str, content: str
) -> Message:
    message = Message(
        tenant_id=tenant_ctx.tenant_id, conversation_id=conversation_id, role=role, content=content
    )
    session.add(message)
    await session.flush()
    return message


async def get_context_messages(
    session: AsyncSession, redis: Redis, tenant_ctx: TenantContext, conversation_id: uuid.UUID
) -> list[ModelMessage]:
    """The recent-history window sent to the model. Tries the Redis short-term cache first;
    Postgres (via list_messages) stays the durable source of truth and is used to repopulate the
    cache on a miss — a cold Redis (fresh deploy, evicted key, expired TTL) degrades to one extra
    DB read, never to lost or wrong history."""
    cached = await short_term.get_recent_messages(redis, tenant_ctx.tenant_id, conversation_id)
    if cached is not None:
        return cached

    history = await list_messages(session, tenant_ctx, conversation_id)
    model_messages = [ModelMessage(role=m.role, content=m.content) for m in history]
    await short_term.replace(redis, tenant_ctx.tenant_id, conversation_id, model_messages)
    return model_messages
