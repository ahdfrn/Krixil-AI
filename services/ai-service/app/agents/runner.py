import json
import time
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import SYSTEM_PROMPT
from app.agents.service import list_agent_steps
from app.ai.base import ModelMessage, ModelProvider, ToolSchema
from app.core.logging import get_logger
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.observability.metrics import AGENT_STEPS
from app.tenancy.context import TenantContext
from app.tools.base import list_tools
from app.tools.service import request_tool_execution

logger = get_logger(__name__)


def _tool_schemas() -> list[ToolSchema]:
    return [
        ToolSchema(
            name=t.name, description=t.description, parameters=t.input_model.model_json_schema()
        )
        for t in list_tools()
    ]


async def _record_step(
    session: AsyncSession,
    agent_run: AgentRun,
    step_number: int,
    step_type: str,
    *,
    tool_name: str | None = None,
    content: dict,
) -> None:
    session.add(
        AgentStep(
            tenant_id=agent_run.tenant_id,
            agent_run_id=agent_run.id,
            step_number=step_number,
            type=step_type,
            tool_name=tool_name,
            content=content,
        )
    )
    AGENT_STEPS.labels(step_type=step_type).inc()
    # A real commit, not just a flush — now that run_agent executes off the request entirely (see
    # app/agents/router.py's _run_agent_in_background), each step needs to become visible to OTHER
    # sessions immediately, specifically a client polling GET /agents/{id}/status from a separate
    # connection while this loop is still running. A flush only pushes SQL within this session's
    # own open transaction; nothing else can see it until commit. expire_on_commit=False
    # (app/db/session.py) means this doesn't invalidate agent_run's already-loaded attributes.
    await session.commit()


def _rebuild_messages(agent_run: AgentRun, steps: list[AgentStep]) -> list[ModelMessage]:
    """Replays a run's persisted steps back into the message list run_agent would have built up
    in memory, so a run that paused for approval (see the `resume` branch below) can pick the
    conversation back up in a fresh background task instead of starting the model over from
    scratch. Mirrors exactly what the main loop below appends per step — a tool_call becomes the
    "Called tool X." assistant line, an observation becomes the "Tool result: ..." user line — so
    the model sees the identical transcript it would have seen if the process had never paused."""
    messages = [
        ModelMessage(role="system", content=SYSTEM_PROMPT),
        ModelMessage(role="user", content=agent_run.goal),
    ]
    for step in steps:
        if step.type == "tool_call":
            messages.append(
                ModelMessage(role="assistant", content=f"Called tool {step.tool_name}.")
            )
        elif step.type == "observation":
            messages.append(
                ModelMessage(role="user", content=f"Tool result: {json.dumps(step.content)}")
            )
    return messages


async def run_agent(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    provider: ModelProvider,
    agent_run: AgentRun,
    model_id: str | None = None,
    *,
    resume: bool = False,
) -> None:
    """UNDERSTAND -> PLAN/SELECT TOOLS -> EXECUTE -> OBSERVE -> (repeat) -> FINAL RESPONSE, per
    docs/architecture/phase4.md. Runs to whichever boundary stops it first: a final answer, a
    budget limit, a cancellation request, or a tool call that needs human approval. Called from a
    background task (see app/agents/router.py's _run_agent_in_background), not inline in the
    request that started it — see docs/architecture/coding-agent.md's "Live, step-by-step
    transcript" section for why.

    model_id follows the same "auto"/None convention as ChatRequest.model (app/chat/router.py's
    _model_kwargs) — None or "auto" means the provider's own configured default; anything else is
    forwarded as a `model=` kwarg on every tool_call this run makes, overriding it for just this
    run without needing a different ModelProvider instance (CloudModelProvider already merges
    **kwargs into its request payload, so this was already how Chat's own per-message model
    switching works for Ollama's multiple local tags).

    resume=True picks a run back up after a HIGH/CRITICAL-risk tool call was approved (see
    app/tools/service.py's approve_execution) instead of starting it fresh — agent_run.step_count
    and its persisted AgentStep rows already reflect everything up through that approved tool's
    resolved observation, so this continues at the next step number with the message history
    rebuilt from those rows, rather than re-asking the model the original goal from nothing.
    """
    if resume:
        steps = await list_agent_steps(session, tenant_ctx, agent_run.id)
        messages = _rebuild_messages(agent_run, steps)
        start_step = agent_run.step_count + 1
    else:
        messages = [
            ModelMessage(role="system", content=SYSTEM_PROMPT),
            ModelMessage(role="user", content=agent_run.goal),
        ]
        start_step = 1
    tools = _tool_schemas()
    model_kwargs = {} if model_id is None or model_id == "auto" else {"model": model_id}
    start = time.monotonic()

    for step_number in range(start_step, agent_run.max_steps + 1):
        # Cancellation (POST /agents/{id}/cancel) is signaled by a *different* request flipping
        # this row's status directly in the DB — our own in-memory agent_run object
        # (expire_on_commit=False) wouldn't otherwise notice a change made by another
        # session/connection, so refresh just this one column each iteration to pick it up. Costs
        # one cheap query per step; checked before the (potentially several-second) model call
        # below so cancelling takes effect between steps, not instantly mid-call — the same
        # "finishes the current action, then stops" shape Claude Code's own interrupt has.
        await session.refresh(agent_run, attribute_names=["status"])
        if agent_run.status == "cancelled":
            agent_run.completed_at = datetime.now(UTC)
            agent_run.step_count = step_number - 1
            logger.info(
                "agent_run_cancelled",
                tenant_id=str(tenant_ctx.tenant_id),
                agent_run_id=str(agent_run.id),
            )
            await session.commit()
            return

        if time.monotonic() - start > agent_run.max_execution_seconds:
            agent_run.status = "stopped"
            agent_run.error_message = "max_execution_seconds exceeded"
            break

        response = await provider.tool_call(messages, tools, **model_kwargs)

        if not response.tool_calls:
            agent_run.final_response = response.content
            agent_run.status = "completed"
            agent_run.step_count = step_number
            await _record_step(
                session,
                agent_run,
                step_number,
                "final_response",
                content={"content": response.content},
            )
            break

        call = response.tool_calls[0]
        agent_run.tool_call_count += 1
        if agent_run.tool_call_count > agent_run.max_tool_calls:
            agent_run.status = "stopped"
            agent_run.error_message = "max_tool_calls exceeded"
            break

        await _record_step(
            session,
            agent_run,
            step_number,
            "tool_call",
            tool_name=call.name,
            content={"arguments": call.arguments},
        )

        try:
            execution = await request_tool_execution(session, tenant_ctx, call.name, call.arguments)
        except HTTPException as exc:
            # A malformed/unpermitted tool call from the model is the model's mistake, not a
            # reason to fail the whole /agents/run request — feed the error back as an
            # observation so the loop (or a smarter model) can react to it, same as a real
            # tool failure would.
            observation = {"error": str(exc.detail)}
            await _record_step(
                session,
                agent_run,
                step_number,
                "observation",
                tool_name=call.name,
                content=observation,
            )
            messages.append(ModelMessage(role="assistant", content=f"Called tool {call.name}."))
            messages.append(
                ModelMessage(role="user", content=f"Tool call failed: {json.dumps(observation)}")
            )
            agent_run.step_count = step_number
            continue

        if execution.status == "pending_approval":
            agent_run.status = "waiting_approval"
            agent_run.pending_execution_id = execution.id
            agent_run.step_count = step_number
            await _record_step(
                session,
                agent_run,
                step_number,
                "observation",
                tool_name=call.name,
                content={"status": "pending_approval", "execution_id": str(execution.id)},
            )
            break

        if execution.status == "completed" and execution.output is not None:
            observation = execution.output
        else:
            observation = {"error": execution.error_message or "unknown error"}
        await _record_step(
            session, agent_run, step_number, "observation", tool_name=call.name, content=observation
        )

        messages.append(ModelMessage(role="assistant", content=f"Called tool {call.name}."))
        messages.append(
            ModelMessage(role="user", content=f"Tool result: {json.dumps(observation)}")
        )
        agent_run.step_count = step_number
    else:
        agent_run.status = "stopped"
        agent_run.error_message = "max_steps exceeded"

    agent_run.completed_at = datetime.now(UTC)
    logger.info(
        "agent_run_finished",
        tenant_id=str(tenant_ctx.tenant_id),
        agent_run_id=str(agent_run.id),
        status=agent_run.status,
        step_count=agent_run.step_count,
    )
    # Terminal states reached without a final _record_step call right after them (max_steps/
    # max_execution_seconds exceeded) need their own commit — every other exit path already got
    # one from _record_step's commit above, but this one doesn't add a step.
    await session.commit()
