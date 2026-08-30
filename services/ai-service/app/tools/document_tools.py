import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.documents import delete_document
from app.storage.dependency import get_storage
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool


class DocumentDeleteInput(BaseModel):
    document_id: uuid.UUID


async def _document_delete_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: DocumentDeleteInput
) -> dict:
    storage = get_storage()
    await delete_document(session, storage, tenant_ctx, params.document_id)
    return {"deleted": True, "document_id": str(params.document_id)}


register_tool(
    Tool(
        name="document.delete",
        description="Permanently delete a document and its chunks. Destructive and irreversible.",
        input_model=DocumentDeleteInput,
        risk_level=RiskLevel.CRITICAL,
        required_permission="document:delete",
        handler=_document_delete_handler,
    )
)
