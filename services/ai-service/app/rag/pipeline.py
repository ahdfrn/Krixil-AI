import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelProvider
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.rag.chunker import chunk_text
from app.rag.parser import UnsupportedFileType, content_type_for, extension_of, parse_document
from app.storage.base import ObjectStorage
from app.tenancy.context import TenantContext

logger = get_logger(__name__)

_EMBEDDING_BATCH_SIZE = 100


async def ingest_document(
    session: AsyncSession,
    storage: ObjectStorage,
    provider: ModelProvider,
    tenant_ctx: TenantContext,
    filename: str,
    content: bytes,
) -> Document:
    settings = get_settings()
    max_bytes = settings.max_document_size_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds the {settings.max_document_size_mb}MB limit",
        )

    try:
        extension = extension_of(filename)
        pages = parse_document(filename, content)
    except UnsupportedFileType as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    document = Document(
        tenant_id=tenant_ctx.tenant_id,
        uploaded_by=tenant_ctx.user_id,
        filename=filename,
        content_type=content_type_for(extension),
        size_bytes=len(content),
        storage_key=f"{tenant_ctx.tenant_id}/{uuid.uuid4()}/{filename}",
        status="processing",
    )
    session.add(document)
    await session.flush()

    try:
        await storage.upload(document.storage_key, content, document.content_type)

        chunk_specs: list[tuple[int, int | None, str]] = []
        chunk_index = 0
        for page_number, page_text in pages:
            for piece in chunk_text(page_text, settings.rag_chunk_size, settings.rag_chunk_overlap):
                chunk_specs.append((chunk_index, page_number, piece))
                chunk_index += 1

        if not chunk_specs:
            document.status = "failed"
            document.error_message = "No extractable text found in this document"
            await session.flush()
            return document

        texts = [spec[2] for spec in chunk_specs]
        embeddings = await _embed_in_batches(provider, texts)

        for (idx, page, piece), vector in zip(chunk_specs, embeddings, strict=True):
            session.add(
                DocumentChunk(
                    tenant_id=tenant_ctx.tenant_id,
                    document_id=document.id,
                    chunk_index=idx,
                    page=page,
                    content=piece,
                    embedding=vector,
                )
            )

        document.status = "ready"
        document.chunk_count = len(chunk_specs)
        await session.flush()
        logger.info(
            "document_ingested",
            tenant_id=str(tenant_ctx.tenant_id),
            document_id=str(document.id),
            chunk_count=document.chunk_count,
        )
        return document

    except HTTPException:
        raise
    except Exception:
        logger.exception("document_ingest_failed", document_id=str(document.id))
        document.status = "failed"
        document.error_message = "Processing failed — see server logs"
        await session.flush()
        return document


async def _embed_in_batches(provider: ModelProvider, texts: list[str]) -> list[list[float]]:
    results: list[list[float]] = []
    for i in range(0, len(texts), _EMBEDDING_BATCH_SIZE):
        batch = texts[i : i + _EMBEDDING_BATCH_SIZE]
        results.extend(await provider.embeddings(batch))
    return results
