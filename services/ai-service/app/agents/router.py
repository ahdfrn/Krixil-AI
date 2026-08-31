import uuid

from fastapi import APIRouter, BackgroundTasks, Depends
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
from app.memory.long_term import extract_and_store_memories
from app.schemas.agent import AgentRunDetailOut, AgentRunOut, AgentRunRequest, AgentStepOut
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(prefix="/agents", tags=["agents"])
model_router = ModelRouter()


@router.post("/run", response_model=AgentRunOut)
async def run(
    payload: AgentRunRequest,
    background_tasks: BackgroundTasks,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunOut:
    agent_run = await create_agent_run(session, tenant_ctx, payload.goal)
    provider = model_router.get_provider()
    await run_agent(session, tenant_ctx, provider, agent_run)
    # Explicit commit here, not left to get_session()'s own post-yield commit — FastAPI runs a
    # yield-dependency's cleanup (including that commit) *after* the response has already been
    # sent to the client (documented FastAPI behavior, not a bug in it). For a fast endpoint the
    # resulting gap is negligible; for this one — a whole planner/executor loop with several LLM
    # calls, writing a run plus multiple steps — it's wide enough that a client polling
    # GET /agents/{id}/status immediately after this call returns would 404 100% of the time in
    # testing (caught live). expire_on_commit=False (app/db/session.py) means committing early
    # here doesn't invalidate agent_run's already-loaded attributes below.
    await session.commit()

    # Same learning pipeline /chat already uses (app/chat/router.py) — a run that reached a real
    # final answer is treated exactly like one chat turn (goal in, final_response out), so it can
    # extract durable memories and become searchable knowledge base content the same way. Only
    # runs with a real final_response qualify — one that stopped, failed, or is still waiting on
    # approval has nothing coherent to learn from yet. agent_run.id/goal are passed as the soft
    # source_conversation_id/title (same pattern as every other caller of this function — no real
    # Conversation row is required, see app/models/document.py) even though this isn't a Chat
    # conversation; extract_and_store_memories itself already respects the user's memory_enabled
    # privacy toggle, same as it does for regular chat.
    if agent_run.final_response:
        background_tasks.add_task(
            extract_and_store_memories,
            tenant_ctx.tenant_id,
            tenant_ctx.user_id,
            agent_run.id,
            agent_run.goal,
            agent_run.goal,
            agent_run.final_response,
        )

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
