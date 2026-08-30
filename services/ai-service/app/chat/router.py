import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelMessage
from app.ai.router import ModelRouter
from app.chat.service import (
    get_context_messages,
    get_conversation_or_404,
    get_or_create_conversation,
    list_conversations,
    list_messages,
    save_message,
)
from app.core.logging import get_logger
from app.core.rate_limit import enforce_chat_rate_limit
from app.core.usage import record_usage
from app.db.redis import get_redis
from app.db.session import AsyncSessionLocal, get_session
from app.memory import short_term
from app.observability.metrics import MODEL_REQUEST_DURATION, TOKEN_USAGE
from app.rag.context import build_rag_context
from app.schemas.chat import (
    ChatRequest,
    ChatResponse,
    ConversationDetailOut,
    ConversationOut,
    MessageOut,
)
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(tags=["chat"])
logger = get_logger(__name__)
model_router = ModelRouter()


@router.post("/chat", response_model=ChatResponse, dependencies=[Depends(enforce_chat_rate_limit)])
async def chat(
    payload: ChatRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> ChatResponse:
    conversation = await get_or_create_conversation(session, tenant_ctx, payload.conversation_id)
    context = await get_context_messages(session, redis, tenant_ctx, conversation.id)

    await save_message(session, tenant_ctx, conversation.id, role="user", content=payload.message)
    await short_term.append_message(
        redis, tenant_ctx.tenant_id, conversation.id, "user", payload.message
    )

    provider = model_router.get_provider()
    rag_message, citations = await build_rag_context(session, tenant_ctx, provider, payload.message)

    model_messages = context + [ModelMessage(role="user", content=payload.message)]
    if rag_message is not None:
        model_messages = [rag_message] + model_messages

    with MODEL_REQUEST_DURATION.labels(provider=provider.name, operation="generate").time():
        response = await provider.generate(model_messages)

    assistant_message = await save_message(
        session, tenant_ctx, conversation.id, role="assistant", content=response.content
    )
    await short_term.append_message(
        redis, tenant_ctx.tenant_id, conversation.id, "assistant", response.content
    )
    await record_usage(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        conversation_id=conversation.id,
        model=response.model,
        usage=response.usage,
    )
    TOKEN_USAGE.labels(model=response.model, token_type="prompt").inc(
        response.usage.get("prompt_tokens", 0)
    )
    TOKEN_USAGE.labels(model=response.model, token_type="completion").inc(
        response.usage.get("completion_tokens", 0)
    )

    logger.info(
        "chat_completed",
        tenant_id=str(tenant_ctx.tenant_id),
        conversation_id=str(conversation.id),
        model=response.model,
        citation_count=len(citations),
    )

    return ChatResponse(
        conversation_id=conversation.id,
        message=MessageOut.model_validate(assistant_message),
        model=response.model,
        citations=citations,
    )


@router.post("/chat/stream", dependencies=[Depends(enforce_chat_rate_limit)])
async def chat_stream(
    payload: ChatRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    redis: Redis = Depends(get_redis),
) -> StreamingResponse:
    # Deliberately NOT using Depends(get_session) here: FastAPI tears down yield-dependencies
    # once the endpoint function returns, which for a StreamingResponse can be before the body
    # generator has actually run. The session is opened and closed entirely inside the
    # generator instead, so its lifetime always matches the streamed response.
    async def event_stream():
        async with AsyncSessionLocal() as session:
            try:
                conversation = await get_or_create_conversation(
                    session, tenant_ctx, payload.conversation_id
                )
                context = await get_context_messages(session, redis, tenant_ctx, conversation.id)

                await save_message(
                    session, tenant_ctx, conversation.id, role="user", content=payload.message
                )
                await short_term.append_message(
                    redis, tenant_ctx.tenant_id, conversation.id, "user", payload.message
                )

                conversation_payload = {
                    "type": "conversation",
                    "conversation_id": str(conversation.id),
                }
                yield f"data: {json.dumps(conversation_payload)}\n\n"

                provider = model_router.get_provider()
                rag_message, citations = await build_rag_context(
                    session, tenant_ctx, provider, payload.message
                )
                if citations:
                    citations_payload = {
                        "type": "citations",
                        "citations": [c.model_dump(mode="json") for c in citations],
                    }
                    yield f"data: {json.dumps(citations_payload)}\n\n"

                model_messages = context + [ModelMessage(role="user", content=payload.message)]
                if rag_message is not None:
                    model_messages = [rag_message] + model_messages

                full_content = ""
                with MODEL_REQUEST_DURATION.labels(
                    provider=provider.name, operation="stream"
                ).time():
                    async for delta in provider.stream(model_messages):
                        full_content += delta
                        yield f"data: {json.dumps({'type': 'chunk', 'delta': delta})}\n\n"
                full_content = full_content.strip()

                assistant_message = await save_message(
                    session, tenant_ctx, conversation.id, role="assistant", content=full_content
                )
                await short_term.append_message(
                    redis, tenant_ctx.tenant_id, conversation.id, "assistant", full_content
                )
                # Streaming responses don't carry a usage payload from most OpenAI-compatible
                # APIs unless a special option is set — token counts aren't tracked here yet;
                # non-streaming /chat is the accurate source for usage in Phase 1.
                await session.commit()

                done_payload = {
                    "type": "done",
                    "message_id": str(assistant_message.id),
                    "model": provider.name,
                }
                yield f"data: {json.dumps(done_payload)}\n\n"
            except Exception:
                await session.rollback()
                logger.exception("chat_stream_failed", tenant_id=str(tenant_ctx.tenant_id))
                yield f"data: {json.dumps({'type': 'error', 'detail': 'stream failed'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/conversations", response_model=list[ConversationOut])
async def get_conversations(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[ConversationOut]:
    conversations = await list_conversations(session, tenant_ctx)
    return [ConversationOut.model_validate(c) for c in conversations]


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
async def get_conversation(
    conversation_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ConversationDetailOut:
    conversation = await get_conversation_or_404(session, tenant_ctx, conversation_id)
    messages = await list_messages(session, tenant_ctx, conversation_id)
    return ConversationDetailOut(
        id=conversation.id,
        title=conversation.title,
        created_at=conversation.created_at,
        messages=[MessageOut.model_validate(m) for m in messages],
    )
