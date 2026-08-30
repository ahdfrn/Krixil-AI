import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import run_agent
from app.agents.service import (
    create_agent_run,
    get_agent_run_or_404,
    list_agent_runs,
    list_agent_steps,
)
from app.ai.router import ModelRouter
from app.db.session import get_session
from app.schemas.agent import AgentRunDetailOut, AgentRunOut, AgentRunRequest, AgentStepOut
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(prefix="/agents", tags=["agents"])
model_router = ModelRouter()


@router.post("/run", response_model=AgentRunOut)
async def run(
    payload: AgentRunRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunOut:
    agent_run = await create_agent_run(session, tenant_ctx, payload.goal)
    provider = model_router.get_provider()
    await run_agent(session, tenant_ctx, provider, agent_run)
    return AgentRunOut.model_validate(agent_run)


@router.get("", response_model=list[AgentRunOut])
async def list_runs(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[AgentRunOut]:
    runs = await list_agent_runs(session, tenant_ctx)
    return [AgentRunOut.model_validate(r) for r in runs]


@router.get("/{agent_run_id}/status", response_model=AgentRunDetailOut)
async def get_status(
    agent_run_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunDetailOut:
    agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
    steps = await list_agent_steps(session, tenant_ctx, agent_run_id)
    return AgentRunDetailOut(
        **AgentRunOut.model_validate(agent_run).model_dump(),
        steps=[AgentStepOut.model_validate(s) for s in steps],
    )
