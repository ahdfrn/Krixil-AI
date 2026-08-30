import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.tenancy.context import TenantContext


async def create_agent_run(session: AsyncSession, tenant_ctx: TenantContext, goal: str) -> AgentRun:
    settings = get_settings()
    agent_run = AgentRun(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        goal=goal,
        status="running",
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        max_execution_seconds=settings.agent_max_execution_seconds,
    )
    session.add(agent_run)
    await session.flush()
    return agent_run


async def get_agent_run_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, agent_run_id: uuid.UUID
) -> AgentRun:
    agent_run = (
        await session.execute(
            select(AgentRun).where(AgentRun.id == agent_run_id, AgentRun.tenant_id == tenant_ctx.tenant_id)
        )
    ).scalar_one_or_none()
    if agent_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent run not found")
    return agent_run


async def list_agent_steps(
    session: AsyncSession, tenant_ctx: TenantContext, agent_run_id: uuid.UUID
) -> list[AgentStep]:
    result = await session.execute(
        select(AgentStep)
        .where(AgentStep.tenant_id == tenant_ctx.tenant_id, AgentStep.agent_run_id == agent_run_id)
        .order_by(AgentStep.step_number.asc())
    )
    return list(result.scalars().all())


async def list_agent_runs(session: AsyncSession, tenant_ctx: TenantContext, limit: int = 50) -> list[AgentRun]:
    result = await session.execute(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_ctx.tenant_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
