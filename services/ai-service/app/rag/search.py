import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelProvider
from app.core.config import get_settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.tenancy.context import TenantContext

# Standard RRF constant (dampens the influence of very-high ranks) — this is the same default
# used across most published/production RRF implementations, not a tuned value.
_RRF_K = 60


@dataclass
class SearchResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    page: int | None
    chunk_index: int
    content: str
    score: float


RankedList = list[tuple[uuid.UUID, int]]


async def _tenant_has_chunks(
    session: AsyncSession, tenant_id: uuid.UUID, document_id: uuid.UUID | None
) -> bool:
    """Cheap existence check, portable across dialects — lets hybrid_search() skip the
    Postgres-only distance/full-text queries entirely when a tenant has no documents yet, which
    is also what keeps /chat's RAG augmentation from touching pgvector-specific SQL for every
    tenant in the offline (SQLite) test suite."""
    query = select(DocumentChunk.id).where(DocumentChunk.tenant_id == tenant_id)
    if document_id is not None:
        query = query.where(DocumentChunk.document_id == document_id)
    result = await session.execute(query.limit(1))
    return result.scalar_one_or_none() is not None


async def _vector_search(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    query_embedding: list[float],
    limit: int,
    document_id: uuid.UUID | None,
) -> RankedList:
    query = select(DocumentChunk.id).where(DocumentChunk.tenant_id == tenant_id)
    if document_id is not None:
        query = query.where(DocumentChunk.document_id == document_id)
    query = query.order_by(DocumentChunk.embedding.cosine_distance(query_embedding)).limit(limit)

    result = await session.execute(query)
    return [(chunk_id, rank) for rank, chunk_id in enumerate((row[0] for row in result.all()), start=1)]


async def _keyword_search(
    session: AsyncSession, tenant_id: uuid.UUID, query_text: str, limit: int, document_id: uuid.UUID | None
) -> RankedList:
    tsvector = func.to_tsvector("english", DocumentChunk.content)
    tsquery = func.plainto_tsquery("english", query_text)

    query = select(DocumentChunk.id).where(DocumentChunk.tenant_id == tenant_id, tsvector.op("@@")(tsquery))
    if document_id is not None:
        query = query.where(DocumentChunk.document_id == document_id)
    query = query.order_by(func.ts_rank(tsvector, tsquery).desc()).limit(limit)

    result = await session.execute(query)
    return [(chunk_id, rank) for rank, chunk_id in enumerate((row[0] for row in result.all()), start=1)]


def _reciprocal_rank_fusion(*ranked_lists: RankedList, top_k: int) -> list[tuple[uuid.UUID, float]]:
    scores: dict[uuid.UUID, float] = {}
    for ranked in ranked_lists:
        for chunk_id, rank in ranked:
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + rank)
    return sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]


async def hybrid_search(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    provider: ModelProvider,
    query_text: str,
    top_k: int | None = None,
    document_id: uuid.UUID | None = None,
) -> list[SearchResult]:
    """Vector search (semantic) + keyword search (exact terms), merged with reciprocal rank
    fusion. RRF over a ML cross-encoder reranker: no extra model to serve, and it's a well
    established, good-enough merge strategy for a Phase 2 corpus size — a real reranker is a
    self-contained upgrade to swap in later without changing this function's signature."""
    settings = get_settings()
    top_k = top_k or settings.rag_top_k

    if not await _tenant_has_chunks(session, tenant_ctx.tenant_id, document_id):
        return []

    query_embedding = (await provider.embeddings([query_text]))[0]
    fetch_limit = top_k * 4

    vector_ranked = await _vector_search(
        session, tenant_ctx.tenant_id, query_embedding, fetch_limit, document_id
    )
    keyword_ranked = await _keyword_search(
        session, tenant_ctx.tenant_id, query_text, fetch_limit, document_id
    )

    fused = _reciprocal_rank_fusion(vector_ranked, keyword_ranked, top_k=top_k)
    if not fused:
        return []

    chunk_ids = [chunk_id for chunk_id, _ in fused]
    rows = (
        await session.execute(
            select(DocumentChunk, Document.filename)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.id.in_(chunk_ids))
        )
    ).all()
    by_id = {chunk.id: (chunk, filename) for chunk, filename in rows}

    results = []
    for chunk_id, score in fused:
        row = by_id.get(chunk_id)
        if row is None:
            continue
        chunk, filename = row
        results.append(
            SearchResult(
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                filename=filename,
                page=chunk.page,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
                score=score,
            )
        )
    return results
