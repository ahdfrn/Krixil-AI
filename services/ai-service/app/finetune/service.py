from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.cloud_provider import CloudModelProvider
from app.core.config import get_settings
from app.evaluation.base import EvalCase
from app.evaluation.eval_tenant import get_or_create_eval_tenant
from app.evaluation.runner import run_evaluation_suite
from app.finetune.dataset import build_dataset
from app.models.finetune_run import FinetuneRun
from app.schemas.finetune import FinetuneEvaluateOut, FinetuneReportRequest
from app.storage.base import ObjectStorage
from app.tenancy.context import TenantContext


async def get_status(
    session: AsyncSession, tenant_ctx: TenantContext
) -> tuple[int, list[FinetuneRun]]:
    dataset = await build_dataset(session, tenant_ctx)
    runs = (
        (
            await session.execute(
                select(FinetuneRun)
                .where(FinetuneRun.tenant_id == tenant_ctx.tenant_id)
                .order_by(FinetuneRun.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    return len(dataset), list(runs)


async def request_run(session: AsyncSession, tenant_ctx: TenantContext) -> FinetuneRun:
    """Records a manual "please run" request — training/'s own poll loop (native Windows, real
    GPU access) picks this up on its next cycle, same as it would notice real readiness on its
    own. The api service never launches training/ itself — see
    docs/architecture/learning-and-memory.md Phase 3 for why that boundary can't be crossed the
    other way (a Linux container can't spawn a process with the Windows host's GPU access)."""
    dataset = await build_dataset(session, tenant_ctx)
    run = FinetuneRun(
        tenant_id=tenant_ctx.tenant_id, status="requested", example_count=len(dataset)
    )
    session.add(run)
    await session.flush()
    return run


async def create_running_row(
    session: AsyncSession, tenant_ctx: TenantContext, example_count: int
) -> FinetuneRun:
    """training/ calls this (via POST /finetune/runs/start) at the start of a self-initiated run
    — one it decided to start on its own readiness check, not a prior manual request — so it has
    a real run to report the outcome back to once finished."""
    run = FinetuneRun(
        tenant_id=tenant_ctx.tenant_id, status="running", example_count=example_count
    )
    session.add(run)
    await session.flush()
    return run


async def evaluate_candidate(
    session: AsyncSession,
    storage: ObjectStorage,
    model_tag: str,
    cases: list[EvalCase] | None = None,
) -> FinetuneEvaluateOut:
    """Runs the existing evaluation harness (app/evaluation/runner.py, built for Phase 5's CI
    gate) against a candidate fine-tuned model, reached the same way any Ollama model is —
    CloudModelProvider pointed at its specific tag, constructed directly rather than through
    ModelRouter (which caches one instance per provider *name*, not per model). `cases` is a
    testing-only override (mirrors run_evaluation_suite's own signature) — the real registered
    cases include Postgres/pgvector-only ones, same reason tests/test_evaluation.py already
    passes an explicit fake case list rather than the real registry."""
    settings = get_settings()
    provider = CloudModelProvider(
        name="finetune-candidate",
        base_url=settings.ollama_base_url,
        api_key="ollama",
        model=model_tag,
        embedding_model=settings.ollama_embedding_model,
    )
    try:
        eval_tenant_ctx = await get_or_create_eval_tenant(session)
        await session.commit()
        run = await run_evaluation_suite(session, eval_tenant_ctx, provider, storage, cases=cases)
        await session.commit()
    finally:
        await provider.aclose()

    return FinetuneEvaluateOut(
        pass_count=run.pass_count, fail_count=run.fail_count, regression=run.regression
    )


async def report_outcome(
    session: AsyncSession, tenant_ctx: TenantContext, payload: FinetuneReportRequest
) -> FinetuneRun:
    run = (
        await session.execute(
            select(FinetuneRun).where(
                FinetuneRun.id == payload.run_id, FinetuneRun.tenant_id == tenant_ctx.tenant_id
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Fine-tune run not found"
        )

    run.status = payload.status
    run.candidate_tag = payload.candidate_tag
    run.promoted_tag = payload.promoted_tag
    run.eval_pass_count = payload.eval_pass_count
    run.eval_fail_count = payload.eval_fail_count
    run.regression = payload.regression
    run.detail = payload.detail
    run.completed_at = datetime.now(UTC)
    await session.flush()
    return run
