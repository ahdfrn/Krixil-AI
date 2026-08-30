import time
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.base import ModelProvider
from app.core.logging import get_logger
from app.evaluation.base import EvalCase, EvalOutcome, list_cases
from app.models.evaluation import EvaluationResult, EvaluationRun
from app.storage.base import ObjectStorage
from app.tenancy.context import TenantContext

logger = get_logger(__name__)


async def _get_baseline(session: AsyncSession, tenant_ctx: TenantContext) -> EvaluationRun | None:
    result = await session.execute(
        select(EvaluationRun)
        .where(EvaluationRun.tenant_id == tenant_ctx.tenant_id, EvaluationRun.status == "completed")
        .order_by(EvaluationRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def run_evaluation_suite(
    session: AsyncSession,
    tenant_ctx: TenantContext,
    provider: ModelProvider,
    storage: ObjectStorage,
    cases: list[EvalCase] | None = None,
) -> EvaluationRun:
    """New Change -> Run Evaluation -> Compare Baseline -> Pass Threshold?, per
    docs/architecture/phase5.md. A case that raises is recorded as a failure with the exception
    message as detail, not left to crash the whole suite — one broken case shouldn't hide the
    results of every other case.

    `cases` defaults to the full global registry (every module in app/evaluation/ registers
    itself on import — see app/evaluation/__init__.py) but can be overridden, which is what lets
    tests exercise this function against a small, self-contained case list instead of the real
    ones (several of which need Postgres/pgvector and can't run on the offline SQLite suite)."""
    if cases is None:
        cases = list_cases()

    baseline = await _get_baseline(session, tenant_ctx)

    run = EvaluationRun(tenant_id=tenant_ctx.tenant_id, status="running")
    session.add(run)
    await session.flush()

    pass_count = 0
    fail_count = 0

    for case in cases:
        start = time.monotonic()
        try:
            outcome = await case.run(session, tenant_ctx, provider, storage)
        except Exception as exc:
            logger.exception("eval_case_errored", case_name=case.name)
            outcome = EvalOutcome(passed=False, details={"error": str(exc)})
        latency_ms = (time.monotonic() - start) * 1000

        session.add(
            EvaluationResult(
                tenant_id=tenant_ctx.tenant_id,
                evaluation_run_id=run.id,
                case_name=case.name,
                category=case.category,
                passed=outcome.passed,
                latency_ms=latency_ms,
                details=outcome.details,
            )
        )
        pass_count += 1 if outcome.passed else 0
        fail_count += 0 if outcome.passed else 1
        logger.info(
            "eval_case_finished",
            case_name=case.name,
            category=case.category,
            passed=outcome.passed,
            latency_ms=round(latency_ms, 1),
        )

    run.pass_count = pass_count
    run.fail_count = fail_count
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    run.regression = pass_count < baseline.pass_count if baseline is not None else None
    await session.flush()

    logger.info(
        "evaluation_run_finished",
        evaluation_run_id=str(run.id),
        pass_count=pass_count,
        fail_count=fail_count,
        regression=run.regression,
    )
    return run
