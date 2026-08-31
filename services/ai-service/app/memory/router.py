import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.memory.long_term import (
    create_memory,
    delete_memory,
    get_memory_settings,
    list_memories,
    set_memory_enabled,
)
from app.schemas.memory import (
    MemoryCreateRequest,
    MemoryOut,
    MemorySettingsOut,
    MemorySettingsUpdateRequest,
)
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(tags=["memory"])


@router.get("/memory", response_model=list[MemoryOut])
async def get_memories(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[MemoryOut]:
    memories = await list_memories(session, tenant_ctx)
    return [MemoryOut.model_validate(m) for m in memories]


@router.post("/memory", response_model=MemoryOut, status_code=status.HTTP_201_CREATED)
async def create_memory_route(
    payload: MemoryCreateRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> MemoryOut:
    memory = await create_memory(session, tenant_ctx, payload.content)
    return MemoryOut.model_validate(memory)


@router.delete("/memory/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory_route(
    memory_id: uuid.UUID,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> None:
    await delete_memory(session, tenant_ctx, memory_id)


@router.get("/memory/settings", response_model=MemorySettingsOut)
async def get_memory_settings_route(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> MemorySettingsOut:
    enabled = await get_memory_settings(session, tenant_ctx)
    return MemorySettingsOut(memory_enabled=enabled)


@router.patch("/memory/settings", response_model=MemorySettingsOut)
async def update_memory_settings_route(
    payload: MemorySettingsUpdateRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> MemorySettingsOut:
    enabled = await set_memory_enabled(session, tenant_ctx, payload.enabled)
    return MemorySettingsOut(memory_enabled=enabled)
