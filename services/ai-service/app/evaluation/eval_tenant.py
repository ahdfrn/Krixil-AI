from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.tenancy.context import TenantContext

# A dedicated, idempotent tenant the eval suite runs against — never used for real login (no
# valid password), just an ORM anchor so eval runs go through the same tenant-scoped code paths
# as everything else. Shared by scripts/run_evaluations.py (CI gate) and app/finetune/router.py's
# candidate-model evaluation — one implementation, not two copies that could drift.
EVAL_TENANT_SLUG = "krixil-evaluation"


async def get_or_create_eval_tenant(session: AsyncSession) -> TenantContext:
    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == EVAL_TENANT_SLUG))
    ).scalar_one_or_none()

    role: Role | None
    user: User | None

    if tenant is None:
        tenant = Tenant(name="Krixil Evaluation", slug=EVAL_TENANT_SLUG)
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

    assert role is not None  # the eval tenant is always created with exactly one role/user
    assert user is not None

    return TenantContext(
        tenant_id=tenant.id, user_id=user.id, role=role.name, permissions=role.permissions
    )
