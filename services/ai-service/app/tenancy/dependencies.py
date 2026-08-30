from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.session import get_session
from app.models.role import Role
from app.models.user import User
from app.tenancy.context import TenantContext


async def get_tenant_context(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    role = await session.get(Role, user.role_id)
    role_name = role.name if role else "unknown"
    permissions = role.permissions if role else []
    return TenantContext(
        tenant_id=user.tenant_id, user_id=user.id, role=role_name, permissions=permissions
    )
