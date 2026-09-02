from urllib.parse import unquote

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.db.session import get_session
from app.models.role import Role
from app.models.user import User
from app.tenancy.context import TenantContext


async def get_tenant_context(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TenantContext:
    role = await session.get(Role, user.role_id)
    role_name = role.name if role else "unknown"
    permissions = role.permissions if role else []
    workspace_root = request.headers.get("X-Krixil-Workspace")
    if workspace_root is not None:
        workspace_root = unquote(workspace_root)
        if "*" not in permissions:
            raise HTTPException(
                status_code=403, detail="Local project selection requires owner permission"
            )
        if (
            not workspace_root
            or len(workspace_root) > 1000
            or any(ord(c) < 32 for c in workspace_root)
        ):
            raise HTTPException(status_code=400, detail="Invalid workspace header")
    return TenantContext(
        tenant_id=user.tenant_id,
        user_id=user.id,
        role=role_name,
        permissions=permissions,
        workspace_root=workspace_root,
    )
