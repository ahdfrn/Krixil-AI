import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit_log
from app.core.logging import get_logger
from app.models.tool_execution import ToolExecution
from app.tenancy.context import TenantContext
from app.tools.base import APPROVAL_REQUIRED_LEVELS, Tool, get_tool

logger = get_logger(__name__)


def _get_tool_or_404(tool_name: str) -> Tool:
    tool = get_tool(tool_name)
    if tool is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown tool '{tool_name}'")
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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=exc.errors())

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


async def _run(session, tenant_ctx: TenantContext, tool: Tool, execution: ToolExecution, validated_input) -> None:
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
        logger.exception("tool_execution_failed", tool_name=tool.name, execution_id=str(execution.id))
        execution.status = "failed"
        execution.error_message = str(exc)

    execution.completed_at = datetime.now(timezone.utc)
    await record_audit_log(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        action=f"tool.{execution.status}",
        resource=tool.name,
        metadata={"execution_id": str(execution.id)},
    )
    await session.flush()


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool execution not found")
    return execution


async def list_executions(session: AsyncSession, tenant_ctx: TenantContext, limit: int = 50) -> list[ToolExecution]:
    result = await session.execute(
        select(ToolExecution)
        .where(ToolExecution.tenant_id == tenant_ctx.tenant_id)
        .order_by(ToolExecution.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def approve_execution(
    session: AsyncSession, tenant_ctx: TenantContext, execution_id: uuid.UUID
) -> ToolExecution:
    if not tenant_ctx.has_permission("tools:approve"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing 'tools:approve' permission")

    execution = await get_execution_or_404(session, tenant_ctx, execution_id)
    if execution.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Execution is not pending approval (status='{execution.status}')",
        )

    tool = _get_tool_or_404(execution.tool_name)
    validated_input = tool.input_model.model_validate(execution.input)

    execution.approved_by = tenant_ctx.user_id
    execution.approved_at = datetime.now(timezone.utc)
    execution.status = "running"
    await session.flush()

    await _run(session, tenant_ctx, tool, execution, validated_input)
    return execution


async def reject_execution(
    session: AsyncSession, tenant_ctx: TenantContext, execution_id: uuid.UUID, reason: str | None
) -> ToolExecution:
    if not tenant_ctx.has_permission("tools:approve"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Missing 'tools:approve' permission")

    execution = await get_execution_or_404(session, tenant_ctx, execution_id)
    if execution.status != "pending_approval":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Execution is not pending approval (status='{execution.status}')",
        )

    execution.status = "rejected"
    execution.error_message = reason
    execution.completed_at = datetime.now(timezone.utc)
    await record_audit_log(
        session,
        tenant_id=tenant_ctx.tenant_id,
        user_id=tenant_ctx.user_id,
        action="tool.rejected",
        resource=execution.tool_name,
        metadata={"execution_id": str(execution.id), "reason": reason},
    )
    await session.flush()
    return execution
