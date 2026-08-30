import json
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.prompts import SYSTEM_PROMPT
from app.ai.base import ModelMessage, ModelProvider, ToolSchema
from app.core.logging import get_logger
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.tenancy.context import TenantContext
from app.tools.base import list_tools
from app.tools.service import request_tool_execution

logger = get_logger(__name__)


def _tool_schemas() -> list[ToolSchema]:
    return [
        ToolSchema(name=t.name, description=t.description, parameters=t.input_model.model_json_schema())
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
    await session.flush()


async def run_agent(
    session: AsyncSession, tenant_ctx: TenantContext, provider: ModelProvider, agent_run: AgentRun
) -> None:
    """UNDERSTAND -> PLAN/SELECT TOOLS -> EXECUTE -> OBSERVE -> (repeat) -> FINAL RESPONSE, per
    docs/architecture/phase4.md. Runs synchronously inside the request to whichever boundary
    stops it first: a final answer, a budget limit, or a tool call that needs human approval —
    no background job queue yet, the same trade-off Phase 2's document ingestion already made.
    """
    messages = [
        ModelMessage(role="system", content=SYSTEM_PROMPT),
        ModelMessage(role="user", content=agent_run.goal),
    ]
    tools = _tool_schemas()
    start = time.monotonic()

    for step_number in range(1, agent_run.max_steps + 1):
        if time.monotonic() - start > agent_run.max_execution_seconds:
            agent_run.status = "stopped"
            agent_run.error_message = "max_execution_seconds exceeded"
            break

        response = await provider.tool_call(messages, tools)

        if not response.tool_calls:
            agent_run.final_response = response.content
            agent_run.status = "completed"
            agent_run.step_count = step_number
            await _record_step(
                session, agent_run, step_number, "final_response", content={"content": response.content}
            )
            break

        call = response.tool_calls[0]
        agent_run.tool_call_count += 1
        if agent_run.tool_call_count > agent_run.max_tool_calls:
            agent_run.status = "stopped"
            agent_run.error_message = "max_tool_calls exceeded"
            break

        await _record_step(
            session, agent_run, step_number, "tool_call", tool_name=call.name, content={"arguments": call.arguments}
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
                session, agent_run, step_number, "observation", tool_name=call.name, content=observation
            )
            messages.append(ModelMessage(role="assistant", content=f"Called tool {call.name}."))
            messages.append(ModelMessage(role="user", content=f"Tool call failed: {json.dumps(observation)}"))
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

        observation = execution.output if execution.status == "completed" else {"error": execution.error_message}
        await _record_step(session, agent_run, step_number, "observation", tool_name=call.name, content=observation)

        messages.append(ModelMessage(role="assistant", content=f"Called tool {call.name}."))
        messages.append(ModelMessage(role="user", content=f"Tool result: {json.dumps(observation)}"))
        agent_run.step_count = step_number
    else:
        agent_run.status = "stopped"
        agent_run.error_message = "max_steps exceeded"

    agent_run.completed_at = datetime.now(timezone.utc)
    logger.info(
        "agent_run_finished",
        tenant_id=str(tenant_ctx.tenant_id),
        agent_run_id=str(agent_run.id),
        status=agent_run.status,
        step_count=agent_run.step_count,
    )
    await session.flush()
