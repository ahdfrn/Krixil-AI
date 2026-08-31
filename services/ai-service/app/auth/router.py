import re
import secrets

import pyotp
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.hashing import hash_password, verify_password
from app.auth.jwt import create_access_token
from app.core.audit import record_audit_log
from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import get_session
from app.models.role import Role
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TenantOut,
    TokenResponse,
    TotpCodeRequest,
    TotpSetupOut,
    TotpStatusOut,
    UserOut,
)

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
            totp_enabled=user.totp_enabled,
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

    if user.totp_enabled:
        if not user.totp_secret:
            # Shouldn't happen — totp_enabled only ever gets set alongside a real secret — but
            # don't silently skip the 2FA check if the data is ever in an inconsistent state.
            raise invalid_credentials
        if not payload.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="2FA code required"
            )
        if not pyotp.TOTP(user.totp_secret).verify(payload.totp_code, valid_window=1):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid 2FA code"
            )

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
            totp_enabled=user.totp_enabled,
            created_at=user.created_at,
        ),
        tenant=TenantOut(id=tenant.id, name=tenant.name, slug=tenant.slug),
    )


@router.post("/2fa/setup", response_model=TotpSetupOut)
async def setup_2fa(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TotpSetupOut:
    # Overwrites any prior unconfirmed secret — nothing was ever "enabled" on it, so there's no
    # state to lose by starting over (e.g. the user re-scans after losing the first QR code).
    secret = pyotp.random_base32()
    current_user.totp_secret = secret
    await session.flush()

    otpauth_url = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email, issuer_name="Krixil AI"
    )
    return TotpSetupOut(secret=secret, otpauth_url=otpauth_url)


@router.post("/2fa/confirm", response_model=TotpStatusOut)
async def confirm_2fa(
    payload: TotpCodeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TotpStatusOut:
    if not current_user.totp_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No pending 2FA setup — call /auth/2fa/setup first",
        )
    if not pyotp.TOTP(current_user.totp_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    current_user.totp_enabled = True
    await session.flush()
    await record_audit_log(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="user.2fa_enabled",
        resource="user",
    )
    return TotpStatusOut(totp_enabled=True)


@router.post("/2fa/disable", response_model=TotpStatusOut)
async def disable_2fa(
    payload: TotpCodeRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TotpStatusOut:
    if not current_user.totp_enabled or not current_user.totp_secret:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="2FA is not enabled")
    # Proof of continued possession of the authenticator, not just an active session — same
    # reasoning as requiring a password to change a password.
    if not pyotp.TOTP(current_user.totp_secret).verify(payload.code, valid_window=1):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid code")

    current_user.totp_secret = None
    current_user.totp_enabled = False
    await session.flush()
    await record_audit_log(
        session,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action="user.2fa_disabled",
        resource="user",
    )
    return TotpStatusOut(totp_enabled=False)
