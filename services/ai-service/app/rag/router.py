import uuid

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import ModelRouter
from app.core.logging import get_logger
from app.db.session import get_session
from app.rag.documents import delete_document, list_documents
from app.rag.pipeline import ingest_document
from app.rag.search import hybrid_search
from app.schemas.document import DocumentOut, SearchRequest, SearchResultOut
from app.storage.base import ObjectStorage
from app.storage.dependency import get_storage
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(tags=["knowledge"])
logger = get_logger(__name__)
model_router = ModelRouter()


@router.post("/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
) -> DocumentOut:
    content = await file.read()
    provider = model_router.get_provider()
    document = await ingest_document(
        session, storage, provider, tenant_ctx, file.filename or "upload", content
    )
    return DocumentOut.model_validate(document)


@router.get("/documents", response_model=list[DocumentOut])
async def get_documents(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[DocumentOut]:
    documents = await list_documents(session, tenant_ctx)
    return [DocumentOut.model_validate(d) for d in documents]


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_document(
    document_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
    storage: ObjectStorage = Depends(get_storage),
) -> None:
    await delete_document(session, storage, tenant_ctx, document_id)


@router.post("/knowledge/search", response_model=list[SearchResultOut])
async def search_knowledge(
    payload: SearchRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[SearchResultOut]:
    provider = model_router.get_provider()
    results = await hybrid_search(
        session,
        tenant_ctx,
        provider,
        payload.query,
        top_k=payload.top_k,
        document_id=payload.document_id,
    )
    return [
        SearchResultOut(
            chunk_id=r.chunk_id,
            document_id=r.document_id,
            filename=r.filename,
            page=r.page,
            chunk_index=r.chunk_index,
            content=r.content,
            score=r.score,
        )
        for r in results
    ]
