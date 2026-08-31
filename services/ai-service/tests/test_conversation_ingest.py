import uuid

from sqlalchemy import select

from app.ai.mock_provider import MockProvider
from app.chat.service import get_or_create_conversation
from app.models.document import Document
from app.rag.conversation_ingest import ingest_conversation_turn
from app.tenancy.context import TenantContext
from tests.helpers import auth_headers, register


async def _tenant_ctx(registered: dict) -> TenantContext:
    return TenantContext(
        tenant_id=uuid.UUID(registered["tenant"]["id"]),
        user_id=uuid.UUID(registered["user"]["id"]),
        role=registered["user"]["role"],
        permissions=["*"],
    )


async def test_ingest_conversation_turn_creates_conversation_sourced_document(
    client, session_factory
):
    registered = await register(client)
    tenant_ctx = await _tenant_ctx(registered)
    provider = MockProvider()

    async with session_factory() as session:
        conversation = await get_or_create_conversation(session, tenant_ctx, None)
        await ingest_conversation_turn(
            session,
            provider,
            tenant_ctx.tenant_id,
            tenant_ctx.user_id,
            conversation.id,
            conversation.title,
            "What database should I use?",
            "Postgres with pgvector is a solid choice for this project.",
        )
        await session.commit()
        conversation_id = conversation.id

    async with session_factory() as session:
        doc = (
            await session.execute(
                select(Document).where(Document.source_conversation_id == conversation_id)
            )
        ).scalar_one()
        assert doc.source == "conversation"
        assert doc.chunk_count >= 1
        assert doc.filename == "Conversation: New conversation"


async def test_ingest_conversation_turn_appends_to_same_document(client, session_factory):
    registered = await register(client)
    tenant_ctx = await _tenant_ctx(registered)
    provider = MockProvider()

    async with session_factory() as session:
        conversation = await get_or_create_conversation(session, tenant_ctx, None)
        await session.commit()
        conversation_id = conversation.id
        conversation_title = conversation.title

    for user_text, assistant_text in [("a", "b"), ("c", "d")]:
        async with session_factory() as session:
            await ingest_conversation_turn(
                session,
                provider,
                tenant_ctx.tenant_id,
                tenant_ctx.user_id,
                conversation_id,
                conversation_title,
                user_text,
                assistant_text,
            )
            await session.commit()

    async with session_factory() as session:
        docs = (
            (
                await session.execute(
                    select(Document).where(Document.source_conversation_id == conversation_id)
                )
            )
            .scalars()
            .all()
        )
        assert len(docs) == 1
        assert docs[0].chunk_count >= 2


# hybrid_search() itself has no offline coverage anywhere in this suite (see app/rag/search.py's
# own docstring: cosine_distance is a Postgres-only pgvector operator, not portable to the SQLite
# engine these tests run against) — that it can actually find conversation-sourced content the
# same way it finds uploaded-document content is verified live, not here.


async def test_delete_conversation_sourced_document_succeeds_with_no_real_file(
    client, session_factory
):
    registered = await register(client)
    headers = auth_headers(registered["access_token"])
    tenant_ctx = await _tenant_ctx(registered)
    provider = MockProvider()

    async with session_factory() as session:
        conversation = await get_or_create_conversation(session, tenant_ctx, None)
        await ingest_conversation_turn(
            session,
            provider,
            tenant_ctx.tenant_id,
            tenant_ctx.user_id,
            conversation.id,
            conversation.title,
            "hello",
            "world",
        )
        await session.commit()

    list_resp = await client.get("/api/v1/documents", headers=headers)
    doc_id = next(d["id"] for d in list_resp.json() if d["source"] == "conversation")

    delete_resp = await client.delete(f"/api/v1/documents/{doc_id}", headers=headers)
    assert delete_resp.status_code == 204
