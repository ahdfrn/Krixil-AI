"""Project Brain (PRD §13) — real indexing and real semantic search, scoped to `host.*`'s real
HOST_ROOT tree (the CLI's primary real usage path; the sandboxed `code.*` workspace is
deliberately not indexed in this pass — see docs/architecture/kirxil-cli-prd.md's §13 status
note). Walks real files via host-runner's `/index-files` (the same recursive walk
`host.search_files` already uses, minus the regex), extracts real symbols
(app/brain/symbols.py), chunks real content (app/rag/chunker.py's chunk_text — the same one
document ingestion already uses), embeds it via
whichever ModelProvider is active, and stores it in a real pgvector table. Each new successful
index run replaces the tenant's previous chunks outright (a fresh full re-index, not incremental).
"""

import uuid
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelProvider
from app.ai.router import ModelRouter
from app.brain.symbols import extract_symbols, guess_language
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.brain_chunk import BrainChunk
from app.models.brain_index_run import BrainIndexRun
from app.rag.chunker import chunk_text
from app.tenancy.context import TenantContext
from app.workspace.scope import host_headers

logger = get_logger(__name__)
model_router = ModelRouter()

_EMBEDDING_BATCH_SIZE = 100
_UNREACHABLE_MESSAGE = (
    "host-runner isn't reachable — is it running? See services/host-runner/README.md."
)


async def _embed_in_batches(provider: ModelProvider, texts: list[str]) -> list[list[float]]:
    """Same batching shape as app/rag/pipeline.py's own _embed_in_batches — not imported directly
    since that one's private to that module, but the real reasoning (bound how much goes into one
    provider.embeddings() call) is identical."""
    results: list[list[float]] = []
    for i in range(0, len(texts), _EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + _EMBEDDING_BATCH_SIZE]
        results.extend(await provider.embeddings(batch))
    return results


async def create_brain_index_run(
    session: AsyncSession, tenant_ctx: TenantContext, directory: str
) -> BrainIndexRun:
    if tenant_ctx.workspace_root:
        raise HTTPException(
            status_code=400, detail="Brain indexing is not yet available in project-scoped sessions"
        )
    index_run = BrainIndexRun(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        directory=directory,
        status="running",
    )
    session.add(index_run)
    await session.flush()
    return index_run


async def get_brain_index_run_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, index_run_id: uuid.UUID
) -> BrainIndexRun:
    index_run = (
        await session.execute(
            select(BrainIndexRun).where(
                BrainIndexRun.id == index_run_id, BrainIndexRun.tenant_id == tenant_ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if index_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Index run not found")
    return index_run


async def get_latest_brain_index_run(
    session: AsyncSession, tenant_ctx: TenantContext
) -> BrainIndexRun | None:
    return (
        await session.execute(
            select(BrainIndexRun)
            .where(BrainIndexRun.tenant_id == tenant_ctx.tenant_id)
            .order_by(BrainIndexRun.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def search_brain(
    session: AsyncSession, tenant_ctx: TenantContext, query: str, limit: int
) -> list[BrainChunk]:
    """Real cosine-similarity search over the tenant's current real index — Postgres/pgvector
    only (EmbeddingVector.comparator_factory), same as app/rag/search.py's own vector search;
    verified against the real Docker stack, not the offline SQLite test suite."""
    provider = model_router.get_provider()
    [query_embedding] = await provider.embeddings([query])
    result = await session.execute(
        select(BrainChunk)
        .where(BrainChunk.tenant_id == tenant_ctx.tenant_id)
        .order_by(BrainChunk.embedding.cosine_distance(query_embedding))
        .limit(limit)
    )
    return list(result.scalars().all())


async def run_brain_index_in_background(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    permissions: list[str],
    index_run_id: uuid.UUID,
    directory: str,
) -> None:
    """Same detached-session, rebuild-from-primitives shape as run_agent_in_background/
    run_swarm_in_background — this runs entirely off the request that scheduled it."""
    tenant_ctx = TenantContext(
        tenant_id=tenant_id, user_id=user_id, role=role, permissions=permissions
    )
    settings = get_settings()

    async with AsyncSessionLocal() as session:
        index_run = await get_brain_index_run_or_404(session, tenant_ctx, index_run_id)
        try:
            async with httpx.AsyncClient(
                timeout=settings.host_runner_timeout_seconds, headers=host_headers()
            ) as client:
                response = await client.get(
                    f"{settings.host_runner_url}/index-files", params={"path": directory}
                )
            response.raise_for_status()
            files = response.json()

            file_count = len(files)
            symbol_count = 0
            chunk_records: list[tuple[str, str | None, str]] = []
            for entry in files:
                path = entry["path"]
                content = entry["content"]
                symbol_count += len(extract_symbols(path, content))
                language = guess_language(path)
                for chunk in chunk_text(
                    content, settings.rag_chunk_size, settings.rag_chunk_overlap
                ):
                    chunk_records.append((path, language, chunk))

            provider = model_router.get_provider()
            embeddings = (
                await _embed_in_batches(provider, [c[2] for c in chunk_records])
                if chunk_records
                else []
            )

            # Fresh full re-index — every previous chunk for this tenant is replaced, not merged.
            await session.execute(
                delete(BrainChunk).where(BrainChunk.tenant_id == tenant_ctx.tenant_id)
            )
            for (path, language, content), embedding in zip(chunk_records, embeddings, strict=True):
                session.add(
                    BrainChunk(
                        tenant_id=tenant_ctx.tenant_id,
                        index_run_id=index_run.id,
                        path=path,
                        language=language,
                        content=content,
                        embedding=embedding,
                    )
                )

            index_run.status = "completed"
            index_run.file_count = file_count
            index_run.symbol_count = symbol_count
            index_run.chunk_count = len(chunk_records)
            index_run.completed_at = datetime.now(UTC)
            await session.commit()
        except httpx.ConnectError:
            index_run.status = "failed"
            index_run.error_message = _UNREACHABLE_MESSAGE
            index_run.completed_at = datetime.now(UTC)
            await session.commit()
        except Exception as exc:
            logger.error("brain_index_failed", index_run_id=str(index_run_id), exc_info=True)
            index_run.status = "failed"
            index_run.error_message = f"Unexpected error while indexing: {exc}"
            index_run.completed_at = datetime.now(UTC)
            await session.commit()
