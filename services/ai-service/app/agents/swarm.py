"""Multi-Agent Swarm (PRD §27) — real parallel sub-agents, not fabricated named specialists.

There is exactly one general agent loop in this codebase (app/agents/runner.py). A "swarm" here
means: one real model call decomposes a goal into independent sub-tasks, each sub-task becomes a
real, ordinary AgentRun (the exact same loop every other verb/goal already uses) run concurrently
via asyncio.gather, and one more real model call synthesizes their actual final_responses into a
combined report. No Architect/Security/Database "agent" exists as a separate running entity — a
child run is differentiated only by its own real sub-task goal text, same reasoning already
documented for §12's Specialized Agents (kirxil-cli-prd.md).

If decomposition doesn't produce at least 2 real sub-tasks (the model returned something that
doesn't parse as a JSON array, or too few), this fails honestly rather than fabricating sub-tasks
or silently running the original goal as a single-member "swarm".
"""

import asyncio
import json
import re
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.runner import run_agent
from app.agents.service import create_agent_run, get_agent_run_or_404
from app.ai.base import ModelMessage, ModelProvider
from app.ai.router import ModelRouter
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.models.agent_run import AgentRun
from app.models.swarm_run import SwarmRun
from app.tenancy.context import TenantContext

logger = get_logger(__name__)
model_router = ModelRouter()

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_DECOMPOSITION_PROMPT_TEMPLATE = (
    "Break the following goal into independent, parallelizable sub-tasks that could genuinely be "
    "worked on at the same time without blocking each other. Produce between 2 and {max_subtasks} "
    "sub-tasks — fewer if the goal is really simpler than that, never more. Respond with ONLY a "
    'JSON array of short, concrete, self-contained task descriptions, e.g. ["...", "..."]. No '
    "other text, no markdown fence."
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You coordinated a team of sub-agents working in parallel on the goal below. Write a concise, "
    "coherent report combining what each sub-task actually produced. Be honest about any sub-task "
    "that failed, timed out, or produced nothing useful — do not paper over it or invent a result "
    "it didn't actually reach."
)


def _parse_subtasks(raw_content: str, max_subtasks: int) -> list[str]:
    """Local models often wrap JSON in a markdown code fence despite instructions not to —
    stripped defensively, same pattern app/memory/long_term.py's _parse_extraction already uses.
    Anything that isn't a clean JSON array of strings is treated as "couldn't decompose" (empty
    list) rather than a hard failure or a fabricated fallback."""
    cleaned = _CODE_FENCE_RE.sub("", raw_content).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    subtasks = [str(item).strip() for item in parsed if str(item).strip()]
    return subtasks[:max_subtasks]


async def decompose_goal(provider: ModelProvider, goal: str, max_subtasks: int) -> list[str]:
    messages = [
        ModelMessage(
            role="system", content=_DECOMPOSITION_PROMPT_TEMPLATE.format(max_subtasks=max_subtasks)
        ),
        ModelMessage(role="user", content=goal),
    ]
    response = await provider.generate(messages)
    return _parse_subtasks(response.content, max_subtasks)


async def synthesize_results(provider: ModelProvider, goal: str, children: list[AgentRun]) -> str:
    parts = []
    for child in children:
        outcome = (
            child.final_response or child.error_message or f"(status: {child.status}, no output)"
        )
        parts.append(f"Sub-task: {child.goal}\nOutcome: {outcome}")
    combined = "\n\n".join(parts)
    messages = [
        ModelMessage(role="system", content=_SYNTHESIS_SYSTEM_PROMPT),
        ModelMessage(role="user", content=f"Original goal: {goal}\n\n{combined}"),
    ]
    response = await provider.generate(messages)
    return response.content


async def create_swarm_run(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    goal: str,
    model_id: str | None = None,
) -> SwarmRun:
    swarm_run = SwarmRun(
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        goal=goal,
        status="running",
        model_id=model_id,
    )
    session.add(swarm_run)
    await session.flush()
    return swarm_run


async def get_swarm_run_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, swarm_run_id: uuid.UUID
) -> SwarmRun:
    swarm_run = (
        await session.execute(
            select(SwarmRun).where(
                SwarmRun.id == swarm_run_id, SwarmRun.tenant_id == tenant_ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if swarm_run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Swarm run not found")
    return swarm_run


async def list_swarm_children(
    session: AsyncSession, tenant_ctx: TenantContext, swarm_run_id: uuid.UUID
) -> list[AgentRun]:
    result = await session.execute(
        select(AgentRun)
        .where(AgentRun.tenant_id == tenant_ctx.tenant_id, AgentRun.swarm_run_id == swarm_run_id)
        .order_by(AgentRun.created_at.asc())
    )
    return list(result.scalars().all())


async def list_swarm_runs(
    session: AsyncSession, tenant_ctx: TenantContext, limit: int = 50
) -> list[SwarmRun]:
    result = await session.execute(
        select(SwarmRun)
        .where(SwarmRun.tenant_id == tenant_ctx.tenant_id)
        .order_by(SwarmRun.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def _run_child_swarm_member(
    tenant_ctx: TenantContext, child_id: uuid.UUID, model_id: str | None
) -> None:
    """Same detached-session, rebuild-from-primitives shape as
    app/agents/router.py's run_agent_in_background, run N times concurrently via asyncio.gather —
    one child's own AsyncSession, never shared across the concurrent tasks (SQLAlchemy's
    AsyncSession isn't safe for concurrent use from more than one coroutine at once)."""
    try:
        async with AsyncSessionLocal() as session:
            child_run = await get_agent_run_or_404(session, tenant_ctx, child_id)
            provider = model_router.get_provider()
            await run_agent(session, tenant_ctx, provider, child_run, model_id)
    except Exception:
        logger.error("swarm_child_failed", agent_run_id=str(child_id), exc_info=True)
        async with AsyncSessionLocal() as fail_session:
            failed_run = await get_agent_run_or_404(fail_session, tenant_ctx, child_id)
            failed_run.status = "failed"
            failed_run.error_message = "Unexpected error while running this sub-task."
            failed_run.completed_at = datetime.now(UTC)
            await fail_session.commit()


async def run_swarm_in_background(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    role: str,
    permissions: list[str],
    swarm_run_id: uuid.UUID,
    model_id: str | None,
    max_subtasks: int,
) -> None:
    tenant_ctx = TenantContext(
        tenant_id=tenant_id, user_id=user_id, role=role, permissions=permissions
    )

    async with AsyncSessionLocal() as session:
        swarm_run = await get_swarm_run_or_404(session, tenant_ctx, swarm_run_id)
        provider = model_router.get_provider()
        subtasks = await decompose_goal(provider, swarm_run.goal, max_subtasks)

        if len(subtasks) < 2:
            swarm_run.status = "failed"
            swarm_run.error_message = (
                "Couldn't decompose this goal into independent sub-tasks — try a more specific "
                "goal, or use `kirxil run`/`kirxil build` for a single-focus task instead."
            )
            swarm_run.completed_at = datetime.now(UTC)
            await session.commit()
            return

        child_ids: list[uuid.UUID] = []
        for subtask_goal in subtasks:
            child_run = await create_agent_run(
                session, tenant_ctx, subtask_goal, model_id, swarm_run_id=swarm_run.id
            )
            child_ids.append(child_run.id)
        swarm_run.subtask_count = len(subtasks)
        await session.commit()

    await asyncio.gather(
        *[_run_child_swarm_member(tenant_ctx, child_id, model_id) for child_id in child_ids]
    )

    async with AsyncSessionLocal() as session:
        swarm_run = await get_swarm_run_or_404(session, tenant_ctx, swarm_run_id)
        children = await list_swarm_children(session, tenant_ctx, swarm_run_id)
        provider = model_router.get_provider()

        if not any(c.final_response for c in children):
            swarm_run.status = "failed"
            swarm_run.error_message = "Every sub-task failed — nothing real to synthesize."
        else:
            swarm_run.synthesis = await synthesize_results(provider, swarm_run.goal, children)
            swarm_run.status = "completed"
        swarm_run.completed_at = datetime.now(UTC)
        await session.commit()
