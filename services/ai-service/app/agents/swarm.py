"""Multi-Agent Swarm (PRD §27) — real parallel sub-agents, not fabricated named specialists.

There is exactly one general agent loop in this codebase (app/agents/runner.py). A "swarm" here
means: one real model call decomposes a goal into sub-tasks (most independent, some may genuinely
depend on an earlier sub-task's real result — see the dependency graph below), each sub-task
becomes a real, ordinary AgentRun (the exact same loop every other verb/goal already uses),
independent ones run concurrently and dependent ones wait for their real prerequisites, and one
more real model call synthesizes their actual final_responses into a combined report. No
Architect/Security/Database "agent" exists as a separate running entity — a child run is
differentiated only by its own real sub-task goal text, same reasoning already documented for
§12's Specialized Agents (kirxil-cli-prd.md).

If decomposition doesn't produce at least 2 real sub-tasks, or the dependency graph the model
returned isn't valid (a dangling reference, a self-reference, or a cycle), this fails honestly
rather than fabricating sub-tasks or silently dropping/reinterpreting a bad edge.
"""

import asyncio
import graphlib
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
from app.models.swarm_task_dependency import SwarmTaskDependency
from app.tenancy.context import TenantContext

logger = get_logger(__name__)
model_router = ModelRouter()

_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)

_DECOMPOSITION_PROMPT_TEMPLATE = (
    "Break the following goal into between 2 and {max_subtasks} sub-tasks. Most sub-tasks should "
    "be independent, but a sub-task MAY depend on one or more earlier sub-tasks finishing first if "
    "it genuinely needs their result (e.g. a testing sub-task depending on what it will test). "
    'Respond with ONLY a JSON array of objects, e.g. [{{"goal": "...", "depends_on": []}}, '
    '{{"goal": "...", "depends_on": [0]}}]. `depends_on` is a list of 0-based indices into this '
    "same array, referring only to EARLIER sub-tasks — never itself, never a later index, never a "
    "cycle. Use an empty list for a sub-task with no dependencies. No other text, no markdown "
    "fence."
)

_SYNTHESIS_SYSTEM_PROMPT = (
    "You coordinated a team of sub-agents working in parallel (some waited on others' results) on "
    "the goal below. Write a concise, coherent report combining what each sub-task actually "
    "produced. Be honest about any sub-task that failed, timed out, or produced nothing useful — "
    "do not paper over it or invent a result it didn't actually reach."
)

Subtask = tuple[str, list[int]]


def _parse_subtasks(raw_content: str, max_subtasks: int) -> list[Subtask]:
    """Local models often wrap JSON in a markdown code fence despite instructions not to —
    stripped defensively, same pattern app/memory/long_term.py's _parse_extraction already uses.
    Anything that isn't a clean JSON array of {goal, depends_on} objects forming a valid,
    acyclic, in-range dependency graph is treated as "couldn't decompose" (empty list) rather
    than a hard failure or a fabricated/silently-reinterpreted fallback — a dangling reference,
    self-reference, or cycle fails the WHOLE decomposition, never just that one edge."""
    cleaned = _CODE_FENCE_RE.sub("", raw_content).strip()
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list) or not parsed:
        return []
    parsed = parsed[:max_subtasks]

    subtasks: list[Subtask] = []
    for item in parsed:
        if not isinstance(item, dict):
            return []
        goal = str(item.get("goal", "")).strip()
        if not goal:
            return []
        raw_deps = item.get("depends_on", [])
        if not isinstance(raw_deps, list):
            return []
        try:
            deps = sorted({int(d) for d in raw_deps})
        except (TypeError, ValueError):
            return []
        subtasks.append((goal, deps))

    n = len(subtasks)
    for i, (_goal, deps) in enumerate(subtasks):
        # Truncation (above) can invalidate a reference to an index that existed before the cap
        # was applied — checked here, after truncation, so that case correctly fails the whole
        # decomposition too, rather than silently dropping the now-broken edge.
        if any(d < 0 or d >= n or d == i for d in deps):
            return []

    graph = {i: set(deps) for i, (_goal, deps) in enumerate(subtasks)}
    try:
        graphlib.TopologicalSorter(graph).prepare()
    except graphlib.CycleError:
        return []

    return subtasks


async def decompose_goal(provider: ModelProvider, goal: str, max_subtasks: int) -> list[Subtask]:
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
        parts.append(f"Sub-task: {child.original_goal or child.goal}\nOutcome: {outcome}")
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


async def list_swarm_dependencies(
    session: AsyncSession, tenant_ctx: TenantContext, child_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Real per-child `depends_on` — a map from each child id to the real sibling ids it waits
    on, built from the real edge table rather than re-deriving it from goal text."""
    if not child_ids:
        return {}
    result = await session.execute(
        select(SwarmTaskDependency).where(
            SwarmTaskDependency.tenant_id == tenant_ctx.tenant_id,
            SwarmTaskDependency.agent_run_id.in_(child_ids),
        )
    )
    deps: dict[uuid.UUID, list[uuid.UUID]] = {cid: [] for cid in child_ids}
    for edge in result.scalars().all():
        deps[edge.agent_run_id].append(edge.depends_on_agent_run_id)
    return deps


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


def _inject_dependency_context(goal_text: str, prerequisites: list[AgentRun]) -> str:
    parts = []
    for dep in prerequisites:
        outcome = dep.final_response or dep.error_message or f"(status: {dep.status}, no output)"
        note = (
            ""
            if dep.status == "completed"
            else " — NOTE: this prerequisite did not complete successfully."
        )
        parts.append(
            f"Prerequisite sub-task: {dep.original_goal or dep.goal}\nOutcome:{note}\n{outcome}"
        )
    context = "\n\n".join(parts)
    return (
        f"Context from prerequisite sub-task(s) that already ran:\n\n{context}\n\n---\n\n"
        f"Your sub-task: {goal_text}"
    )


async def _run_child_swarm_member(
    tenant_ctx: TenantContext,
    child_id: uuid.UUID,
    dependency_ids: list[uuid.UUID],
    model_id: str | None,
) -> None:
    """Same detached-session, rebuild-from-primitives shape as
    app/agents/router.py's run_agent_in_background — one child's own AsyncSession, never shared
    across concurrently-running children (SQLAlchemy's AsyncSession isn't safe for concurrent use
    from more than one coroutine at once). A child with real prerequisites gets its `goal`
    rewritten to include their real output before it ever starts — done here, inside the same
    try/except as the run itself, so a failure while loading a prerequisite also honestly marks
    this child failed rather than being silently swallowed by the scheduler."""
    try:
        async with AsyncSessionLocal() as session:
            child_run = await get_agent_run_or_404(session, tenant_ctx, child_id)
            if dependency_ids:
                prerequisites = [
                    await get_agent_run_or_404(session, tenant_ctx, dep_id)
                    for dep_id in dependency_ids
                ]
                child_run.original_goal = child_run.goal
                child_run.goal = _inject_dependency_context(child_run.goal, prerequisites)
            child_run.status = "running"
            await session.commit()
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


async def _run_dag(
    tenant_ctx: TenantContext,
    child_ids: list[uuid.UUID],
    edges: dict[int, set[int]],
    model_id: str | None,
) -> None:
    """Runs every child respecting the real dependency graph — a child starts the instant its own
    prerequisites finish, not on a fixed "wave" boundary (so independent work started later can
    still overlap with an earlier, still-running dependent chain). Uses stdlib graphlib's
    incremental interface, the same graph structure already validated (acyclic, in-range) during
    parsing — one dependency-graph implementation, not two."""
    ts: graphlib.TopologicalSorter[int] = graphlib.TopologicalSorter(edges)
    ts.prepare()  # cycle-free by construction (validated in _parse_subtasks) — real defense in
    # depth, not decorative: if this ever does raise, let it propagate rather than loop forever.
    running: dict[asyncio.Task, int] = {}
    while ts.is_active():
        for idx in ts.get_ready():
            dependency_ids = [child_ids[d] for d in edges.get(idx, ())]
            task = asyncio.create_task(
                _run_child_swarm_member(tenant_ctx, child_ids[idx], dependency_ids, model_id)
            )
            running[task] = idx
        if not running:
            break
        done, _pending = await asyncio.wait(running.keys(), return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            ts.done(running.pop(task))


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
                "Couldn't decompose this goal into a valid set of sub-tasks — try a more specific "
                "goal, or use `kirxil run`/`kirxil build` for a single-focus task instead."
            )
            swarm_run.completed_at = datetime.now(UTC)
            await session.commit()
            return

        child_ids: list[uuid.UUID] = []
        for goal_text, deps in subtasks:
            child_run = await create_agent_run(
                session,
                tenant_ctx,
                goal_text,
                model_id,
                swarm_run_id=swarm_run.id,
                initial_status="running" if not deps else "queued",
            )
            child_ids.append(child_run.id)
        for i, (_goal_text, deps) in enumerate(subtasks):
            for d in deps:
                session.add(
                    SwarmTaskDependency(
                        tenant_id=tenant_ctx.tenant_id,
                        agent_run_id=child_ids[i],
                        depends_on_agent_run_id=child_ids[d],
                    )
                )
        swarm_run.subtask_count = len(subtasks)
        await session.commit()

    edges = {i: set(deps) for i, (_goal_text, deps) in enumerate(subtasks)}
    await _run_dag(tenant_ctx, child_ids, edges, model_id)

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
