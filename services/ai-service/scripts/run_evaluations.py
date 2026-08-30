"""Runs the AI evaluation harness against a real Postgres/Redis/MinIO stack (same config the app
itself uses via .env / environment). Exits 1 if any case failed or this run regressed against the
previous baseline — meant to gate a CI/CD deploy step, per docs/architecture/phase5.md.

Usage: python scripts/run_evaluations.py   (run from services/ai-service, with the stack up and
migrations applied — same prerequisites as running the app itself).
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

import app.evaluation  # noqa: E402,F401  imported for its side effect: registers every eval case
from app.ai.router import ModelRouter  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.evaluation.runner import run_evaluation_suite  # noqa: E402
from app.models.role import Role  # noqa: E402
from app.models.tenant import Tenant  # noqa: E402
from app.models.user import User  # noqa: E402
from app.storage.dependency import get_storage  # noqa: E402
from app.tenancy.context import TenantContext  # noqa: E402

# A dedicated, idempotent tenant the eval suite runs against — never used for real login (no
# valid password), just an ORM anchor so eval runs go through the same tenant-scoped code paths
# as everything else.
_EVAL_TENANT_SLUG = "krixil-evaluation"


async def _get_or_create_eval_tenant(session) -> TenantContext:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == _EVAL_TENANT_SLUG))
    ).scalar_one_or_none()

    if tenant is None:
        tenant = Tenant(name="Krixil Evaluation", slug=_EVAL_TENANT_SLUG)
        session.add(tenant)
        await session.flush()

        role = Role(tenant_id=tenant.id, name="owner", permissions=["*"])
        session.add(role)
        await session.flush()

        user = User(
            tenant_id=tenant.id,
            email="eval@krixil.internal",
            password_hash="not-a-real-login",
            role_id=role.id,
        )
        session.add(user)
        await session.flush()
    else:
        role = (
            (await session.execute(select(Role).where(Role.tenant_id == tenant.id)))
            .scalars()
            .first()
        )
        user = (
            (await session.execute(select(User).where(User.tenant_id == tenant.id)))
            .scalars()
            .first()
        )

    return TenantContext(
        tenant_id=tenant.id, user_id=user.id, role=role.name, permissions=role.permissions
    )


async def main() -> int:
    provider = ModelRouter().get_provider()
    storage = get_storage()
    await storage.ensure_bucket()

    async with AsyncSessionLocal() as session:
        tenant_ctx = await _get_or_create_eval_tenant(session)
        await session.commit()

    async with AsyncSessionLocal() as session:
        run = await run_evaluation_suite(session, tenant_ctx, provider, storage)
        await session.commit()

    regression_note = " (REGRESSION vs baseline)" if run.regression else ""
    summary = f"passed, {run.fail_count} failed{regression_note}"
    print(f"\nEvaluation run {run.id}: {run.pass_count} {summary}")

    if run.fail_count > 0 or run.regression:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
