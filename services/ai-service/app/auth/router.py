import re
import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.hashing import hash_password, verify_password
from app.auth.jwt import create_access_token
from app.core.audit import record_audit_log
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TenantOut, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()
logger = get_logger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.lower()).strip("-") or "tenant"
    return f"{base}-{secrets.token_hex(3)}"


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    tenant = Tenant(name=payload.tenant_name, slug=_slugify(payload.tenant_name))
    session.add(tenant)
    await session.flush()

    owner_role = Role(tenant_id=tenant.id, name="owner", permissions=["*"])
    session.add(owner_role)
    await session.flush()

    user = User(
        tenant_id=tenant.id,
        email=payload.email.lower(),
        password_hash=hash_password(payload.password),
        role_id=owner_role.id,
    )
    session.add(user)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Registration conflict, please retry"
        ) from exc

    await record_audit_log(
        session,
        tenant_id=tenant.id,
        user_id=user.id,
        action="user.register",
        resource="user",
        metadata={"email": user.email},
    )

    logger.info("user_registered", tenant_id=str(tenant.id), user_id=str(user.id))

    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=owner_role.name)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserOut(
            id=user.id,
            email=user.email,
            role=owner_role.name,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
        tenant=TenantOut(id=tenant.id, name=tenant.name, slug=tenant.slug),
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest, session: AsyncSession = Depends(get_session)
) -> TokenResponse:
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid tenant, email, or password"
    )

    tenant = (
        await session.execute(select(Tenant).where(Tenant.slug == payload.tenant_slug))
    ).scalar_one_or_none()
    if tenant is None:
        raise invalid_credentials

    user = (
        await session.execute(
            select(User).where(User.tenant_id == tenant.id, User.email == payload.email.lower())
        )
    ).scalar_one_or_none()
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise invalid_credentials

    role = await session.get(Role, user.role_id)
    role_name = role.name if role else "unknown"

    await record_audit_log(
        session, tenant_id=tenant.id, user_id=user.id, action="user.login", resource="user"
    )

    logger.info("user_login", tenant_id=str(tenant.id), user_id=str(user.id))

    token = create_access_token(user_id=user.id, tenant_id=tenant.id, role=role_name)
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt_expire_minutes * 60,
        user=UserOut(
            id=user.id,
            email=user.email,
            role=role_name,
            is_active=user.is_active,
            created_at=user.created_at,
        ),
        tenant=TenantOut(id=tenant.id, name=tenant.name, slug=tenant.slug),
    )
