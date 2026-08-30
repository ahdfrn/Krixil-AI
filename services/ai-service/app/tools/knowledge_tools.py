import uuid

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.router import ModelRouter
from app.rag.search import hybrid_search
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool

model_router = ModelRouter()


class KnowledgeSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int | None = Field(default=None, ge=1, le=50)
    document_id: uuid.UUID | None = None


async def _knowledge_search_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: KnowledgeSearchInput
) -> dict:
    provider = model_router.get_provider()
    results = await hybrid_search(
        session,
        tenant_ctx,
        provider,
        params.query,
        top_k=params.top_k,
        document_id=params.document_id,
    )
    return {
        "results": [
            {
                "document_id": str(r.document_id),
                "filename": r.filename,
                "page": r.page,
                "chunk_index": r.chunk_index,
                "content": r.content,
                "score": r.score,
            }
            for r in results
        ]
    }


register_tool(
    Tool(
        name="knowledge.search",
        description="Search the tenant's uploaded documents for content relevant to a query.",
        input_model=KnowledgeSearchInput,
        risk_level=RiskLevel.LOW,
        required_permission="knowledge:read",
        handler=_knowledge_search_handler,
    )
)
