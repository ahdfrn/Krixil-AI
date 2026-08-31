import json
import re
import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelMessage
from app.ai.router import ModelRouter
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.models.user_memory import UserMemory
from app.rag.conversation_ingest import ingest_conversation_turn
from app.tenancy.context import TenantContext

logger = get_logger(__name__)

_EXTRACTION_SYSTEM_PROMPT = (
    "Analyze this chat exchange and extract two different kinds of things worth keeping:\n"
    '1. "memories": durable, personally-relevant facts about the user worth remembering across '
    "future conversations — their name, stated preferences, ongoing projects, or facts they "
    "share about themselves.\n"
    '2. "notes": anything else worth being able to search up later — a decision that was made, '
    "an explanation given, or an important detail discussed — even if it isn't personally about "
    "the user (e.g. a technical choice for a project).\n"
    "Ignore one-off questions and small talk that fit neither category. Respond with ONLY a JSON "
    'object of the exact shape {"memories": [...], "notes": [...]}, each a list of short strings '
    "in the same language the user wrote in (empty lists if nothing qualifies). No other text."
)

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def _parse_extraction(raw_content: str) -> tuple[list[str], list[str]]:
    """Local models often wrap JSON in a markdown code fence despite instructions not to —
    stripped defensively before parsing. Anything that isn't a clean {"memories": [...], "notes":
    [...]} object is treated as "nothing extracted" rather than a hard failure, since this is
    best-effort. Returns (memories, notes)."""
    cleaned = _CODE_FENCE_RE.sub("", raw_content).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        return [], []
    memories = parsed.get("memories", [])
    notes = parsed.get("notes", [])
    if not isinstance(memories, list) or not isinstance(notes, list):
        return [], []
    return (
        [str(item).strip() for item in memories if str(item).strip()],
        [str(item).strip() for item in notes if str(item).strip()],
    )


async def extract_and_store_memories(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    conversation_title: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """Runs off the request's critical path (FastAPI BackgroundTasks for /chat,
    asyncio.create_task for /chat/stream — see app/chat/router.py) — opens its own session,
    entirely detached from the request that triggered it, and never raises: a malformed response
    or provider error just means nothing gets remembered from this turn, not a crashed background
    task or a failed chat response (which has already been sent by the time this runs).

    Also doubles as the "worth indexing" signal for the auto-expanding knowledge base (Track
    Phase 2, see docs/architecture/learning-and-memory.md): this same call asks for two different
    things — "memories" (personal facts, stored as UserMemory rows, shown in Settings) and "notes"
    (anything else worth being searchable later, e.g. a decision or explanation that isn't
    personally about the user). Either one being non-empty is enough to index the raw turn into
    the conversation's searchable document — one LLM call serving both purposes, not two.
    """
    try:
        async with AsyncSessionLocal() as session:
            user = (
                await session.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
            if user is None or not user.memory_enabled:
                return

            provider = ModelRouter().get_provider()
            response = await provider.generate(
                [
                    ModelMessage(role="system", content=_EXTRACTION_SYSTEM_PROMPT),
                    ModelMessage(
                        role="user",
                        content=f"User: {user_message}\nAssistant: {assistant_message}",
                    ),
                ]
            )

            memories, notes = _parse_extraction(response.content)
            if not memories and not notes:
                return

            for fact in memories:
                session.add(
                    UserMemory(
                        tenant_id=tenant_id,
                        user_id=user_id,
                        content=fact,
                        source_conversation_id=conversation_id,
                    )
                )

            await ingest_conversation_turn(
                session,
                provider,
                tenant_id,
                user_id,
                conversation_id,
                conversation_title,
                user_message,
                assistant_message,
            )

            await session.commit()
    except Exception:
        logger.exception("memory_extraction_failed", tenant_id=str(tenant_id), user_id=str(user_id))


async def build_memory_context(
    session: AsyncSession, tenant_ctx: TenantContext
) -> ModelMessage | None:
    """Same shape as app.rag.context.build_rag_context: a system message to prepend, or None when
    there's nothing to add (memory disabled, or no facts yet)."""
    user = (
        await session.execute(select(User).where(User.id == tenant_ctx.user_id))
    ).scalar_one_or_none()
    if user is None or not user.memory_enabled:
        return None

    memories = await list_memories(session, tenant_ctx)
    if not memories:
        return None

    lines = "\n".join(f"- {m.content}" for m in memories)
    content = f"Here's what you remember about this user from past conversations:\n{lines}"
    return ModelMessage(role="system", content=content)


async def list_memories(session: AsyncSession, tenant_ctx: TenantContext) -> list[UserMemory]:
    settings = get_settings()
    result = await session.execute(
        select(UserMemory)
        .where(
            UserMemory.tenant_id == tenant_ctx.tenant_id, UserMemory.user_id == tenant_ctx.user_id
        )
        .order_by(UserMemory.created_at.desc())
        .limit(settings.memory_max_facts)
    )
    return list(result.scalars().all())


async def create_memory(
    session: AsyncSession, tenant_ctx: TenantContext, content: str
) -> UserMemory:
    memory = UserMemory(
        tenant_id=tenant_ctx.tenant_id, user_id=tenant_ctx.user_id, content=content
    )
    session.add(memory)
    await session.flush()
    return memory


async def delete_memory(
    session: AsyncSession, tenant_ctx: TenantContext, memory_id: uuid.UUID
) -> None:
    memory = (
        await session.execute(
            select(UserMemory).where(
                UserMemory.id == memory_id,
                UserMemory.tenant_id == tenant_ctx.tenant_id,
                UserMemory.user_id == tenant_ctx.user_id,
            )
        )
    ).scalar_one_or_none()
    if memory is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Memory not found")
    await session.delete(memory)


async def get_memory_settings(session: AsyncSession, tenant_ctx: TenantContext) -> bool:
    user = (
        await session.execute(select(User).where(User.id == tenant_ctx.user_id))
    ).scalar_one_or_none()
    return bool(user and user.memory_enabled)


async def set_memory_enabled(
    session: AsyncSession, tenant_ctx: TenantContext, enabled: bool
) -> bool:
    user = (
        await session.execute(select(User).where(User.id == tenant_ctx.user_id))
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user.memory_enabled = enabled
    await session.flush()
    return user.memory_enabled
