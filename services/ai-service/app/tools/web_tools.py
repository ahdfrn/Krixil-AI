import httpx
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


class WebSearchInput(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    max_results: int = Field(default=5, ge=1, le=10)


async def _web_search_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: WebSearchInput
) -> dict:
    settings = get_settings()
    if not settings.tavily_api_key:
        raise ValueError("Web search isn't configured yet — set TAVILY_API_KEY.")

    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            TAVILY_SEARCH_URL,
            headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
            json={
                "query": params.query,
                "max_results": params.max_results,
                "include_answer": "basic",
            },
        )
        response.raise_for_status()
        data = response.json()

    return {
        "answer": data.get("answer"),
        "results": [
            {
                "title": r["title"],
                "url": r["url"],
                "content": r["content"],
                "score": r["score"],
            }
            for r in data.get("results", [])
        ],
    }


register_tool(
    Tool(
        name="web.search",
        description="Search the live web for current information not in the tenant's own "
        "knowledge base — news, recent events, or anything outside what's been uploaded.",
        input_model=WebSearchInput,
        risk_level=RiskLevel.LOW,
        required_permission="web:search",
        handler=_web_search_handler,
    )
)
