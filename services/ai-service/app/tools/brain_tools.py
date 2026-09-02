from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.service import search_brain
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool


class BrainSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=50)


async def _brain_search_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: BrainSearchInput
) -> dict:
    chunks = await search_brain(session, tenant_ctx, params.query, params.limit)
    return {
        "results": [
            {"path": c.path, "language": c.language, "content": c.content} for c in chunks
        ]
    }


register_tool(
    Tool(
        name="brain.search",
        description="Real semantic search over this project's real, already-indexed source code "
        "and docs (run `kirxil brain` to build/refresh the index first — this returns nothing if "
        "no index exists yet). Finds content by meaning, not just exact text match, unlike "
        "host.search_files' regex search.",
        input_model=BrainSearchInput,
        # LOW, same tier as knowledge.search/host.search_files — read-only, no side effects.
        risk_level=RiskLevel.LOW,
        required_permission="host:read",
        handler=_brain_search_handler,
    )
)
