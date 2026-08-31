from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.finetune.dataset import build_dataset
from app.finetune.service import (
    create_running_row,
    evaluate_candidate,
    get_status,
    report_outcome,
    request_run,
)
from app.schemas.finetune import (
    FinetuneDatasetOut,
    FinetuneEvaluateOut,
    FinetuneEvaluateRequest,
    FinetuneReportRequest,
    FinetuneRunOut,
    FinetuneStartRunRequest,
    FinetuneStatusOut,
)
from app.storage.base import ObjectStorage
from app.storage.dependency import get_storage
from app.tenancy.context import TenantContext
from app.tenancy.dependencies import get_tenant_context

router = APIRouter(tags=["finetune"])


@router.get("/finetune/dataset", response_model=FinetuneDatasetOut)
async def get_dataset(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> FinetuneDatasetOut:
    rows = await build_dataset(session, tenant_ctx)
    return FinetuneDatasetOut(example_count=len(rows), rows=rows)


@router.get("/finetune/status", response_model=FinetuneStatusOut)
async def get_finetune_status(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> FinetuneStatusOut:
    example_count, runs = await get_status(session, tenant_ctx)
    settings = get_settings()
    return FinetuneStatusOut(
        example_count=example_count,
        min_examples=settings.finetune_min_examples,
        ready=example_count >= settings.finetune_min_examples,
        runs=[FinetuneRunOut.model_validate(r) for r in runs],
    )


@router.post("/finetune/run", response_model=FinetuneRunOut)
async def trigger_run(
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> FinetuneRunOut:
    run = await request_run(session, tenant_ctx)
    return FinetuneRunOut.model_validate(run)


@router.post("/finetune/runs/start", response_model=FinetuneRunOut)
async def start_self_initiated_run(
    payload: FinetuneStartRunRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> FinetuneRunOut:
    """training/'s poll loop calls this when it decides to start a run on its own readiness
    check (not a prior manual request from Settings, which already has its own "requested" row
    via POST /finetune/run) — creates the row it will report the outcome against."""
    run = await create_running_row(session, tenant_ctx, payload.example_count)
    return FinetuneRunOut.model_validate(run)


@router.post("/finetune/evaluate", response_model=FinetuneEvaluateOut)
async def evaluate_run(
    payload: FinetuneEvaluateRequest,
    storage: ObjectStorage = Depends(get_storage),
    session: AsyncSession = Depends(get_session),
) -> FinetuneEvaluateOut:
    return await evaluate_candidate(session, storage, payload.model_tag)


@router.post("/finetune/report", response_model=FinetuneRunOut)
async def report_run(
    payload: FinetuneReportRequest,
    tenant_ctx: TenantContext = Depends(get_tenant_context),
    session: AsyncSession = Depends(get_session),
) -> FinetuneRunOut:
    run = await report_outcome(session, tenant_ctx, payload)
    return FinetuneRunOut.model_validate(run)
