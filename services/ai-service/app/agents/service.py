import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.tenancy.context import TenantContext


async def create_agent_run(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    goal: str,
    model_id: str | None = None,
    max_steps: int | None = None,
    swarm_run_id: uuid.UUID | None = None,
    initial_status: str = "running",
    runtime: str = "native",
) -> AgentRun:
    settings = get_settings()
    # min(), not a straight override — a client-requested budget can only ever be tighter than
    # the deployment's own configured ceiling, never looser (see AgentRunRequest.max_steps).
    effective_max_steps = (
        settings.agent_max_steps if max_steps is None else min(max_steps, settings.agent_max_steps)
    )
    agent_run = AgentRun(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        goal=goal,
        workspace_root=tenant_ctx.workspace_root,
        status=initial_status,
        model_id=model_id,
        runtime=runtime,
        max_steps=effective_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        max_execution_seconds=settings.agent_max_execution_seconds,
        swarm_run_id=swarm_run_id,
    )
    session.add(agent_run)
    await session.flush()
    return agent_run


async def get_agent_run_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, agent_run_id: uuid.UUID
) -> AgentRun:
    agent_run = (
        await session.execute(
            select(AgentRun).where(
                AgentRun.id == agent_run_id, AgentRun.tenant_id == tenant_ctx.tenant_id
            )
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
        # step_number alone isn't a stable order — a tool_call and its observation share one
        # loop iteration's step_number (by design, see app/agents/runner.py), and without a
        # secondary key Postgres is free to return the two in either order. Real bug, caught live
        # via the CLI's transcript printing an observation before the tool_call that produced it
        # (confirmed by querying this exact endpoint directly: the API itself returned them
        # swapped, not a client-side rendering bug). created_at is µs-resolution and Python-side
        # (see TimestampMixin), assigned when each step is committed — since round two's
        # _record_step now commits per step individually, tool_call and observation are always
        # genuinely sequential commits, so this is a real, reliable tiebreaker, not a coincidence.
        .order_by(AgentStep.step_number.asc(), AgentStep.created_at.asc())
    )
    return list(result.scalars().all())


async def list_agent_runs(
    session: AsyncSession, tenant_ctx: TenantContext, limit: int = 50
) -> list[AgentRun]:
    result = await session.execute(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_ctx.tenant_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
