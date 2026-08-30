import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.storage.base import ObjectStorage
from app.tenancy.context import TenantContext


async def list_documents(session: AsyncSession, tenant_ctx: TenantContext) -> list[Document]:
    result = await session.execute(
        select(Document)
        .where(Document.tenant_id == tenant_ctx.tenant_id)
        .order_by(Document.created_at.desc())
    )
    return list(result.scalars().all())


async def get_document_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, document_id: uuid.UUID
) -> Document:
    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.tenant_id == tenant_ctx.tenant_id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return document


async def delete_document(
    session: AsyncSession, storage: ObjectStorage, tenant_ctx: TenantContext, document_id: uuid.UUID
) -> None:
    document = await get_document_or_404(session, tenant_ctx, document_id)
    await storage.delete(document.storage_key)
    await session.delete(document)  # cascades to document_chunks via ondelete="CASCADE"
