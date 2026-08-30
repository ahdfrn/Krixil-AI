import uuid
from datetime import UTC, datetime

from app.ai.mock_provider import MockProvider
from app.evaluation.base import EvalCase, EvalOutcome
from app.evaluation.runner import run_evaluation_suite
from app.models.evaluation import EvaluationRun
from app.tenancy.context import TenantContext
from tests.fakes import FakeObjectStorage
from tests.helpers import register

# These are passed explicitly via run_evaluation_suite(cases=...) rather than registered into the
# global registry: any import touching app.evaluation.base also runs app/evaluation/__init__.py,
# which registers the *real* cases too — several of which need Postgres/pgvector and can't run on
# this offline SQLite suite. Passing an explicit list keeps these tests fully isolated from that.


async def _passing_case(session, tenant_ctx, provider, storage) -> EvalOutcome:
    return EvalOutcome(passed=True, details={})


async def _failing_case(session, tenant_ctx, provider, storage) -> EvalOutcome:
    return EvalOutcome(passed=False, details={"reason": "intentional"})


async def _erroring_case(session, tenant_ctx, provider, storage) -> EvalOutcome:
    raise RuntimeError("boom")


_FAKE_CASES = [
    EvalCase(name="test.always_passes", category="test", run=_passing_case),
    EvalCase(name="test.always_fails", category="test", run=_failing_case),
    EvalCase(name="test.always_errors", category="test", run=_erroring_case),
]


async def _tenant_ctx_from_registration(client) -> TenantContext:
    registered = await register(client)
    return TenantContext(
        tenant_id=uuid.UUID(registered["tenant"]["id"]),
        user_id=uuid.UUID(registered["user"]["id"]),
        role=registered["user"]["role"],
        permissions=["*"],
    )


async def test_run_counts_pass_fail_and_treats_errors_as_failures(client, session_factory):
    tenant_ctx = await _tenant_ctx_from_registration(client)
    provider = MockProvider()
    storage = FakeObjectStorage()

    async with session_factory() as session:
        run = await run_evaluation_suite(session, tenant_ctx, provider, storage, cases=_FAKE_CASES)
        await session.commit()

    assert run.status == "completed"
    assert run.pass_count == 1
    assert run.fail_count == 2  # always_fails + always_errors (caught, not raised)
    assert run.regression is None  # no prior baseline to compare against


async def test_regression_detected_when_pass_count_drops_below_baseline(client, session_factory):
    tenant_ctx = await _tenant_ctx_from_registration(client)
    provider = MockProvider()
    storage = FakeObjectStorage()

    async with session_factory() as session:
        baseline = EvaluationRun(
            tenant_id=tenant_ctx.tenant_id,
            status="completed",
            pass_count=99,
            fail_count=0,
            completed_at=datetime.now(UTC),
        )
        session.add(baseline)
        await session.commit()

    async with session_factory() as session:
        run = await run_evaluation_suite(session, tenant_ctx, provider, storage, cases=_FAKE_CASES)
        await session.commit()

    assert run.regression is True


async def test_no_regression_when_pass_count_meets_or_beats_baseline(client, session_factory):
    tenant_ctx = await _tenant_ctx_from_registration(client)
    provider = MockProvider()
    storage = FakeObjectStorage()

    async with session_factory() as session:
        baseline = EvaluationRun(
            tenant_id=tenant_ctx.tenant_id,
            status="completed",
            pass_count=1,
            fail_count=2,
            completed_at=datetime.now(UTC),
        )
        session.add(baseline)
        await session.commit()

    async with session_factory() as session:
        run = await run_evaluation_suite(session, tenant_ctx, provider, storage, cases=_FAKE_CASES)
        await session.commit()

    assert run.regression is False


async def test_evaluation_results_are_recorded_per_case(client, session_factory):
    from sqlalchemy import select

    from app.models.evaluation import EvaluationResult

    tenant_ctx = await _tenant_ctx_from_registration(client)
    provider = MockProvider()
    storage = FakeObjectStorage()

    async with session_factory() as session:
        run = await run_evaluation_suite(session, tenant_ctx, provider, storage, cases=_FAKE_CASES)
        await session.commit()

    async with session_factory() as session:
        results = (
            (
                await session.execute(
                    select(EvaluationResult).where(EvaluationResult.evaluation_run_id == run.id)
                )
            )
            .scalars()
            .all()
        )

    by_name = {r.case_name: r for r in results}
    assert by_name["test.always_passes"].passed is True
    assert by_name["test.always_fails"].passed is False
    assert by_name["test.always_errors"].passed is False
    assert "boom" in by_name["test.always_errors"].details["error"]


async def test_default_cases_are_the_full_global_registry(client, session_factory):
    """Sanity check on the *other* half of the contract: with no `cases=` override, the runner
    picks up whatever app/evaluation/__init__.py registered (rag/tool/latency/cost/citation
    cases) — proving the default path isn't accidentally always empty."""
    from app.evaluation.base import list_cases

    tenant_ctx = await _tenant_ctx_from_registration(client)
    provider = MockProvider()
    storage = FakeObjectStorage()

    async with session_factory() as session:
        run = await run_evaluation_suite(session, tenant_ctx, provider, storage)
        await session.commit()

    assert run.pass_count + run.fail_count == len(list_cases())
    assert len(list_cases()) >= 5
