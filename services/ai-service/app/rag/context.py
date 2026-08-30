from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelMessage, ModelProvider
from app.rag.search import hybrid_search
from app.schemas.chat import CitationOut
from app.tenancy.context import TenantContext

_SYSTEM_PREFIX = (
    "Use the following context from the tenant's documents if it's relevant to the user's "
    "question. Cite sources as [1], [2], etc. matching the numbering below. If the context "
    "isn't relevant, answer normally and ignore it.\n\n"
)


async def build_rag_context(
    session: AsyncSession, tenant_ctx: TenantContext, provider: ModelProvider, query: str
) -> tuple[ModelMessage | None, list[CitationOut]]:
    """Returns (system message to prepend, citations for the response) — (None, []) when the
    tenant has no documents, so /chat's context-building is a no-op for tenants without a KB
    (and never touches the Postgres-only search query for them — see search._tenant_has_chunks)."""
    results = await hybrid_search(session, tenant_ctx, provider, query)
    if not results:
        return None, []

    blocks = [f"[{i}] (source: {r.filename})\n{r.content}" for i, r in enumerate(results, start=1)]
    system_message = ModelMessage(role="system", content=_SYSTEM_PREFIX + "\n\n".join(blocks))

    citations = [
        CitationOut(
            document_id=r.document_id, filename=r.filename, page=r.page, chunk_index=r.chunk_index
        )
        for r in results
    ]
    return system_message, citations
