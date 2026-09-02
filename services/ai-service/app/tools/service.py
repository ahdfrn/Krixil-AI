import asyncio
import time
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.logging import get_logger
from app.models.agent_run import AgentRun
from app.models.agent_step import AgentStep
from app.models.tool_execution import ToolExecution
from app.observability.metrics import TOOL_EXECUTION_DURATION
from app.observability.tracing import get_tracer
from app.tenancy.context import TenantContext
from app.tools.base import APPROVAL_REQUIRED_LEVELS, Tool, get_tool

logger = get_logger(__name__)


def _get_tool_or_404(tool_name: str) -> Tool:
    tool = get_tool(tool_name)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool '{tool_name}'"
        )
    return tool


async def request_tool_execution(
    session: AsyncSession, tenant_ctx: TenantContext, tool_name: str, raw_input: dict
) -> ToolExecution:
    """Schema validation -> permission check -> risk check -> (execute now, or park pending
    approval) -> audit log. Matches the flow in docs/architecture/phase3.md 1:1."""
    tool = _get_tool_or_404(tool_name)

    if not tenant_ctx.has_permission(tool.required_permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission '{tool.required_permission}'",
        )

    try:
        validated_input = tool.input_model.model_validate(raw_input)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=exc.errors()
        ) from exc

    if tool.risk_classifier is not None:
        block_reason = tool.risk_classifier(validated_input)
        if block_reason is not None:
            return await _block(session, tenant_ctx, tool, validated_input, block_reason)

    requires_approval = tool.risk_level in APPROVAL_REQUIRED_LEVELS
    execution = ToolExecution(
        tenant_id=tenant_ctx.tenant_id,
        requested_by=tenant_ctx.user_id,
        tool_name=tool.name,
        risk_level=tool.risk_level.value,
        input=validated_input.model_dump(mode="json"),
        status="pending_approval" if requires_approval else "running",
    )
    session.add(execution)
    await session.flush()

    if requires_approval:
        await record_audit_log(
            session,
            tenant_id=tenant_ctx.tenant_id,
            user_id=tenant_ctx.user_id,
            action="tool.approval_requested",
            resource=tool.name,
            metadata={"execution_id": str(execution.id), "risk_level": tool.risk_level.value},
        )
        logger.info(
            "tool_approval_requested",
            tenant_id=str(tenant_ctx.tenant_id),
            tool_name=tool.name,
            execution_id=str(execution.id),
        )
        return execution

    await _run(session, tenant_ctx, tool, execution, validated_input)
    return execution


async def _block(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    tool: Tool,
    validated_input,
    block_reason: str,
) -> ToolExecution:
    """A real, hard, terminal outcome distinct from "pending_approval" — never offered to a human
    to approve at all (see app/tools/risk_rules.py's docstring for why). The agent loop
    (app/agents/runner.py) doesn't need special-casing for this: its existing "anything other than
    completed/pending_approval is an error" branch already turns this into a real observation the
    model sees and can react to, the same as any other tool failure."""
    execution = ToolExecution(
        tenant_id=tenant_ctx.tenant_id,
        requested_by=tenant_ctx.user_id,
        tool_name=tool.name,
        risk_level=tool.risk_level.value,
        input=validated_input.model_dump(mode="json"),
        status="blocked",
        error_message=f"Blocked: {block_reason} — this command was not executed.",
        completed_at=datetime.now(UTC),
    )
    session.add(execution)
    await session.flush()
    await record_audit_log(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        action="tool.blocked",
        resource=tool.name,
        metadata={"execution_id": str(execution.id), "reason": block_reason},
    )
    logger.warning(
        "tool_blocked",
        tenant_id=str(tenant_ctx.tenant_id),
        tool_name=tool.name,
        execution_id=str(execution.id),
        reason=block_reason,
    )
    return execution


async def _run(
    session, tenant_ctx: TenantContext, tool: Tool, execution: ToolExecution, validated_input
) -> None:
    start = time.monotonic()
    with get_tracer().start_as_current_span("tool.execute") as span:
        span.set_attribute("tool.name", tool.name)
        span.set_attribute("tool.risk_level", tool.risk_level.value)
        try:
            output = await asyncio.wait_for(
                tool.handler(session, tenant_ctx, validated_input), timeout=tool.timeout_seconds
            )
            execution.output = output
            execution.status = "completed"
        except TimeoutError:
            execution.status = "failed"
            execution.error_message = f"Tool execution timed out after {tool.timeout_seconds}s"
        except Exception as exc:
            logger.exception(
                "tool_execution_failed", tool_name=tool.name, execution_id=str(execution.id)
            )
            execution.status = "failed"
            execution.error_message = str(exc)

    TOOL_EXECUTION_DURATION.labels(tool_name=tool.name, status=execution.status).observe(
        time.monotonic() - start
    )
    execution.completed_at = datetime.now(UTC)
    await record_audit_log(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        action=f"tool.{execution.status}",
        resource=tool.name,
        metadata={"execution_id": str(execution.id)},
    )
    await session.flush()


async def _resolve_paused_agent_run(
    session: AsyncSession, execution: ToolExecution
) -> AgentRun | None:
    """A tool call an agent run paused on (app/agents/runner.py, execution.status ==
    "pending_approval") is resolved through this generic endpoint, not by the run loop itself —
    the run loop already returned its HTTP response and isn't running anymore. Without this, the
    run's own persisted status/steps stayed frozen at "waiting_approval" / "pending_approval"
    forever, even after the underlying ToolExecution genuinely completed — the Agents page kept
    showing "Waiting on your approval" indefinitely with no way to see the real result (caught
    live: approved a real code.run_command, the sandbox ran it, but the UI never reflected it).
    Mirrors what run_agent() itself writes for a normal (non-paused) tool completion.

    Returns the AgentRun to resume (app/tools/router.py schedules a background continuation of
    run_agent(resume=True) on it) when the approved tool actually ran — a real Permission Engine
    has to let the agent keep working after a HIGH-risk step is approved, not just hand back that
    one tool's result and quit. A rejection or a failed approved tool still ends the run: there's
    nothing useful to resume with (rejected) or the same failure would likely just repeat
    (failed) — either way returns None so the caller doesn't schedule anything."""
    agent_run = (
        await session.execute(
            select(AgentRun).where(
                AgentRun.pending_execution_id == execution.id,
                AgentRun.status == "waiting_approval",
            )
        )
    ).scalar_one_or_none()
    if agent_run is None:
        return None

    last_step = (
        await session.execute(
            select(AgentStep)
            .where(AgentStep.agent_run_id == agent_run.id)
            .order_by(AgentStep.step_number.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    resume_target: AgentRun | None = None
    if execution.status == "completed":
        agent_run.status = "running"
        resume_target = agent_run
        result_content = execution.output or {}
    elif execution.status == "rejected":
        agent_run.status = "stopped"
        agent_run.completed_at = datetime.now(UTC)
        result_content = {"rejected": True, "reason": execution.error_message}
    else:
        agent_run.status = "failed"
        agent_run.error_message = execution.error_message
        agent_run.completed_at = datetime.now(UTC)
        result_content = {"error": execution.error_message or "unknown error"}

    if last_step is not None and last_step.type == "observation":
        last_step.content = result_content
    agent_run.pending_execution_id = None
    await session.flush()
    return resume_target


async def get_execution_or_404(
    session: AsyncSession, tenant_ctx: TenantContext, execution_id: uuid.UUID
) -> ToolExecution:
    execution = (
        await session.execute(
            select(ToolExecution).where(
                ToolExecution.id == execution_id, ToolExecution.tenant_id == tenant_ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if execution is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Tool execution not found"
        )
    return execution


async def list_executions(
    session: AsyncSession, tenant_ctx: TenantContext, limit: int = 50
) -> list[ToolExecution]:
    result = await session.execute(
        select(ToolExecution)
        .where(ToolExecution.tenant_id == tenant_ctx.tenant_id)
        .order_by(ToolExecution.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def approve_execution(
    session: AsyncSession, tenant_ctx: TenantContext, execution_id: uuid.UUID
) -> tuple[ToolExecution, AgentRun | None]:
    if not tenant_ctx.has_permission("tools:approve"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing 'tools:approve' permission"
        )

    execution = await get_execution_or_404(session, tenant_ctx, execution_id)
    if execution.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Execution is not pending approval (status='{execution.status}')",
        )

    tool = _get_tool_or_404(execution.tool_name)
    validated_input = tool.input_model.model_validate(execution.input)

    execution.approved_by = tenant_ctx.user_id
    execution.approved_at = datetime.now(UTC)
    execution.status = "running"
    await session.flush()

    await _run(session, tenant_ctx, tool, execution, validated_input)
    resume_target = await _resolve_paused_agent_run(session, execution)
    return execution, resume_target


async def reject_execution(
    session: AsyncSession, tenant_ctx: TenantContext, execution_id: uuid.UUID, reason: str | None
) -> ToolExecution:
    if not tenant_ctx.has_permission("tools:approve"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Missing 'tools:approve' permission"
        )

    execution = await get_execution_or_404(session, tenant_ctx, execution_id)
    if execution.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Execution is not pending approval (status='{execution.status}')",
        )

    execution.status = "rejected"
    execution.error_message = reason
    execution.completed_at = datetime.now(UTC)
    await record_audit_log(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        action="tool.rejected",
        resource=execution.tool_name,
        metadata={"execution_id": str(execution.id), "reason": reason},
    )
    await session.flush()
    # Rejection never resumes the run — see _resolve_paused_agent_run's docstring.
    await _resolve_paused_agent_run(session, execution)
    return execution
