import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import run_agent
from app.agents.service import (
    create_agent_run,
    get_agent_run_or_404,
    list_agent_runs,
    list_agent_steps,
)
from app.ai.catalog import validate_model_id
from app.ai.router import ModelRouter
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal, get_session
from app.memory.long_term import extract_and_store_memories
from app.schemas.agent import AgentRunDetailOut, AgentRunOut, AgentRunRequest, AgentStepOut
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(prefix="/agents", tags=["agents"])
model_router = ModelRouter()
logger = get_logger(__name__)


async def run_agent_in_background(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    permissions: list[str],
    agent_run_id: uuid.UUID,
    model_id: str | None,
    *,
    resume: bool = False,
) -> None:
    """Runs the whole planner/executor loop off the request entirely, so POST /agents/run can
    return the moment the run row exists instead of blocking for up to max_execution_seconds —
    the change that makes the Code page's transcript update live (poll GET /agents/{id}/status)
    instead of showing nothing until a single big result lands at the end, same reason
    app/memory/long_term.py's extract_and_store_memories already opens its own session directly:
    this runs entirely detached from the request that scheduled it, on a plain TenantContext
    rebuilt from primitives (never pass an ORM object or the request's own session across a
    background-task boundary — same lesson learned twice already in this codebase, see
    docs/architecture/learning-and-memory.md).

    resume=True is how a run comes back to life after pausing on a HIGH/CRITICAL-risk tool call
    that just got approved (app/tools/router.py's approve endpoint schedules this exact call) —
    forwarded straight through to run_agent, which rebuilds the message history from the run's
    persisted steps instead of starting the goal over."""
    tenant_ctx = TenantContext(
        tenant_id=tenant_id, user_id=user_id, role=role, permissions=permissions
    )
    try:
        async with AsyncSessionLocal() as session:
            agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
            provider = model_router.get_provider()
            await run_agent(session, tenant_ctx, provider, agent_run, model_id, resume=resume)
            final_response = agent_run.final_response
            goal = agent_run.goal
    except Exception:
        logger.error("agent_run_background_failed", agent_run_id=str(agent_run_id), exc_info=True)
        async with AsyncSessionLocal() as fail_session:
            failed_run = await get_agent_run_or_404(fail_session, tenant_ctx, agent_run_id)
            failed_run.status = "failed"
            failed_run.error_message = "Unexpected error while running the agent."
            failed_run.completed_at = datetime.now(UTC)
            await fail_session.commit()
        return

    # Same learning pipeline /chat already uses (app/chat/router.py) — a run that reached a real
    # final answer is treated exactly like one chat turn (goal in, final_response out), so it can
    # extract durable memories and become searchable knowledge base content the same way. Only
    # runs with a real final_response qualify — one that stopped, failed, or is still waiting on
    # approval has nothing coherent to learn from yet. agent_run_id/goal are passed as the soft
    # source_conversation_id/title (same pattern as every other caller of this function — no real
    # Conversation row is required, see app/models/document.py) even though this isn't a Chat
    # conversation; extract_and_store_memories itself already respects the user's memory_enabled
    # privacy toggle, same as it does for regular chat. Awaited directly (not scheduled again) —
    # we're already off the request's critical path.
    if final_response:
        await extract_and_store_memories(
            tenant_id, user_id, agent_run_id, goal, goal, final_response
        )


@router.post("/run", response_model=AgentRunOut)
async def run(
    payload: AgentRunRequest,
    background_tasks: BackgroundTasks,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunOut:
    await validate_model_id(payload.model)
    agent_run = await create_agent_run(
        session, tenant_ctx, payload.goal, payload.model, payload.max_steps
    )
    # Explicit commit here, not left to get_session()'s own post-yield commit — FastAPI runs a
    # yield-dependency's cleanup (including that commit) *after* the response has already been
    # sent to the client (documented FastAPI behavior, not a bug in it). The background task below
    # opens its own separate session/connection, so it needs this row to be genuinely committed,
    # not just flushed within this request's still-open transaction, before it can see it.
    await session.commit()
    background_tasks.add_task(
        run_agent_in_background,
        tenant_ctx.tenant_id,
        tenant_ctx.user_id,
        tenant_ctx.role,
        tenant_ctx.permissions,
        agent_run.id,
        payload.model,
    )
    return AgentRunOut.model_validate(agent_run)


@router.post("/{agent_run_id}/cancel", response_model=AgentRunOut)
async def cancel(
    agent_run_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> AgentRunOut:
    """Claude Code's own "esc to interrupt" for a run still in progress. Doesn't kill anything
    directly — the loop itself notices on its next iteration (see run_agent's per-step status
    refresh in app/agents/runner.py) and stops there, so cancelling still takes a few seconds if a
    model call is already in flight. A no-op (not an error) if the run already reached a terminal
    state by the time this lands — the natural end of a race against the loop finishing on its
    own, not a client mistake worth surfacing."""
    agent_run = await get_agent_run_or_404(session, tenant_ctx, agent_run_id)
    if agent_run.status == "running":
        agent_run.status = "cancelled"
        await session.commit()
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
