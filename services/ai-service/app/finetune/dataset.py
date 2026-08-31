from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.message import Message
from app.models.user import User
from app.tenancy.context import TenantContext


async def build_dataset(session: AsyncSession, tenant_ctx: TenantContext) -> list[dict]:
    """Real conversation turns (user message -> assistant reply pairs) as {"prompt", "completion"}
    rows for fine-tuning (training/run.py consumes this shape directly). Gated by the same
    memory_enabled toggle Phases 1-2 already use for "is my data eligible to be learned from" —
    one privacy switch, not a second one to explain. A minimum-length filter drops trivially short
    exchanges ("hi" / "ok") since Unsloth's own guidance is that dataset quality matters as much
    as row count, and this schema has no explicit feedback/rating signal to filter on more
    precisely than that.
    """
    user = (
        await session.execute(select(User).where(User.id == tenant_ctx.user_id))
    ).scalar_one_or_none()
    if user is None or not user.memory_enabled:
        return []

    settings = get_settings()
    min_chars = settings.finetune_min_message_chars

    messages = (
        await session.execute(
            select(Message)
            .where(Message.tenant_id == tenant_ctx.tenant_id)
            .order_by(Message.conversation_id, Message.created_at)
        )
    ).scalars()

    rows: list[dict] = []
    pending_prompt: str | None = None
    current_conversation_id = None

    for message in messages:
        if message.conversation_id != current_conversation_id:
            current_conversation_id = message.conversation_id
            pending_prompt = None

        if message.role == "user":
            pending_prompt = message.content
        elif message.role == "assistant" and pending_prompt is not None:
            if len(pending_prompt) >= min_chars and len(message.content) >= min_chars:
                rows.append({"prompt": pending_prompt, "completion": message.content})
            pending_prompt = None

    return rows
