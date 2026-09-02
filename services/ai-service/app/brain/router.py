from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.service import (
    create_brain_index_run,
    get_latest_brain_index_run,
    run_brain_index_in_background,
    search_brain,
)
from app.db.session import get_session
from app.schemas.brain import (
    BrainIndexRequest,
    BrainIndexRunOut,
    BrainSearchRequest,
    BrainSearchResultOut,
)
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(prefix="/brain", tags=["brain"])


@router.post("/index", response_model=BrainIndexRunOut)
async def index(
    payload: BrainIndexRequest,
    background_tasks: BackgroundTasks,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> BrainIndexRunOut:
    """PRD §13 Project Brain — real indexing of a real directory under HOST_ROOT. Returns
    immediately with status="running"; poll GET /brain/status for the real result, same async
    pattern as /agents/run and /agents/swarm."""
    index_run = await create_brain_index_run(session, tenant_ctx, payload.directory)
    await session.commit()
    background_tasks.add_task(
        run_brain_index_in_background,
        tenant_ctx.tenant_id,
        tenant_ctx.user_id,
        tenant_ctx.role,
        tenant_ctx.permissions,
        index_run.id,
        payload.directory,
    )
    return BrainIndexRunOut.model_validate(index_run)


@router.get("/status", response_model=BrainIndexRunOut | None)
async def get_status(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> BrainIndexRunOut | None:
    """The tenant's most recent real index run — null if `kirxil brain` has never been run here."""
    index_run = await get_latest_brain_index_run(session, tenant_ctx)
    return BrainIndexRunOut.model_validate(index_run) if index_run else None


@router.post("/search", response_model=list[BrainSearchResultOut])
async def search(
    payload: BrainSearchRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> list[BrainSearchResultOut]:
    chunks = await search_brain(session, tenant_ctx, payload.query, payload.limit)
    return [
        BrainSearchResultOut(path=c.path, language=c.language, content=c.content) for c in chunks
    ]
