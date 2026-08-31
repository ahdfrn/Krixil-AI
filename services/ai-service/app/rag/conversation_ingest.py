import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelProvider
from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.rag.chunker import chunk_text


async def ingest_conversation_turn(
    session: AsyncSession,
    provider: ModelProvider,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    conversation_title: str,
    user_message: str,
    assistant_message: str,
) -> None:
    """Appends a chat turn to the conversation's own searchable document — one document per
    conversation (found by source_conversation_id, created lazily on the first indexed turn), not
    one per turn, so the Knowledge page doesn't fill up with near-duplicate entries and citations
    get a stable source label. New chunks continue from the document's current chunk_count rather
    than restarting at 0, since this document keeps growing across calls. No real file backs this
    document — storage_key is a sentinel, never actually uploaded (see app/models/document.py).

    Takes conversation_id/conversation_title as plain values rather than a Conversation object
    fetched by the caller — this runs from a background task on its own session, and a real
    cross-session read of a just-created Conversation row raced the triggering request's own
    commit in practice (found live: the row wasn't visible yet, so lookups silently found
    nothing). Passing plain values instead avoids that read entirely, same reason
    user_message/assistant_message are already passed as plain strings rather than re-queried.
    """
    document = (
        await session.execute(
            select(Document).where(
                Document.tenant_id == tenant_id,
                Document.source_conversation_id == conversation_id,
            )
        )
    ).scalar_one_or_none()

    if document is None:
        document = Document(
            tenant_id=tenant_id,
            uploaded_by=user_id,
            filename=f"Conversation: {conversation_title}",
            content_type="text/plain",
            size_bytes=0,
            storage_key=f"conversation:{conversation_id}",
            status="ready",
            chunk_count=0,
            source="conversation",
            source_conversation_id=conversation_id,
        )
        session.add(document)
        await session.flush()

    settings = get_settings()
    text = f"User: {user_message}\nAssistant: {assistant_message}"
    pieces = chunk_text(text, settings.rag_chunk_size, settings.rag_chunk_overlap)
    if not pieces:
        return

    embeddings = await provider.embeddings(pieces)
    start_index = document.chunk_count
    for offset, (piece, vector) in enumerate(zip(pieces, embeddings, strict=True)):
        session.add(
            DocumentChunk(
                tenant_id=tenant_id,
                document_id=document.id,
                chunk_index=start_index + offset,
                page=None,
                content=piece,
                embedding=vector,
            )
        )
    document.chunk_count = start_index + len(pieces)
    document.size_bytes += len(text.encode("utf-8"))
    await session.flush()
