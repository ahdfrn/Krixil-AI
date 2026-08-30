import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.tool import RejectExecutionRequest, ToolExecutionOut, ToolOut
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context
from app.tools.base import list_tools
from app.tools.service import (
    approve_execution,
    get_execution_or_404,
    list_executions,
    reject_execution,
    request_tool_execution,
)

router = APIRouter(tags=["tools"])


@router.get("/tools", response_model=list[ToolOut])
async def get_tools() -> list[ToolOut]:
    return [
        ToolOut(
            name=t.name,
            description=t.description,
            risk_level=t.risk_level.value,
            required_permission=t.required_permission,
            input_schema=t.input_model.model_json_schema(),
        )
        for t in list_tools()
    ]


@router.post("/tools/{tool_name}/execute", response_model=ToolExecutionOut)
async def execute_tool(
    tool_name: str,
    payload: dict,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ToolExecutionOut:
    execution = await request_tool_execution(session, tenant_ctx, tool_name, payload)
    return ToolExecutionOut.model_validate(execution)


@router.get("/tools/executions", response_model=list[ToolExecutionOut])
async def get_executions(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[ToolExecutionOut]:
    executions = await list_executions(session, tenant_ctx)
    return [ToolExecutionOut.model_validate(e) for e in executions]


@router.get("/tools/executions/{execution_id}", response_model=ToolExecutionOut)
async def get_execution(
    execution_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ToolExecutionOut:
    execution = await get_execution_or_404(session, tenant_ctx, execution_id)
    return ToolExecutionOut.model_validate(execution)


@router.post("/tools/executions/{execution_id}/approve", response_model=ToolExecutionOut)
async def approve(
    execution_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ToolExecutionOut:
    execution = await approve_execution(session, tenant_ctx, execution_id)
    return ToolExecutionOut.model_validate(execution)


@router.post("/tools/executions/{execution_id}/reject", response_model=ToolExecutionOut)
async def reject(
    execution_id: uuid.UUID,
    payload: RejectExecutionRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> ToolExecutionOut:
    execution = await reject_execution(session, tenant_ctx, execution_id, payload.reason)
    return ToolExecutionOut.model_validate(execution)
