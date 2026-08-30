from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_record import UsageRecord
from app.tenancy.context import TenantContext
from app.tools.base import RiskLevel, Tool, register_tool


class UsageSummaryInput(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


async def _usage_summary_handler(
    session: AsyncSession, tenant_ctx: TenantContext, params: UsageSummaryInput
) -> dict:
    since = datetime.now(timezone.utc) - timedelta(days=params.days)

    totals_row = (
        await session.execute(
            select(
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
            ).where(UsageRecord.tenant_id == tenant_ctx.tenant_id, UsageRecord.created_at >= since)
        )
    ).one()
    request_count, prompt_tokens, completion_tokens = totals_row

    by_model_rows = (
        await session.execute(
            select(
                UsageRecord.model,
                func.count(UsageRecord.id),
                func.coalesce(func.sum(UsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(UsageRecord.completion_tokens), 0),
            )
            .where(UsageRecord.tenant_id == tenant_ctx.tenant_id, UsageRecord.created_at >= since)
            .group_by(UsageRecord.model)
        )
    ).all()

    return {
        "period_days": params.days,
        "request_count": request_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "by_model": [
            {"model": model, "request_count": count, "prompt_tokens": p_tok, "completion_tokens": c_tok}
            for model, count, p_tok, c_tok in by_model_rows
        ],
    }


register_tool(
    Tool(
        name="usage.get_summary",
        description="Get a summary of this tenant's AI usage (requests and token counts) over a recent period.",
        input_model=UsageSummaryInput,
        risk_level=RiskLevel.LOW,
        required_permission="usage:read",
        handler=_usage_summary_handler,
    )
)
