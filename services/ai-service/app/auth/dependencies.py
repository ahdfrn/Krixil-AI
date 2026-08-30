from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt import decode_access_token
from app.core.config import get_settings
from app.db.session import get_session
from app.models.user import User

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_access_token(token)
    except JWTError as exc:
        raise credentials_error from exc

    user = await session.get(User, payload.user_id)

    # Cross-check the DB record against the token, not just the signature: a token whose
    # claims no longer match the user's real tenant/active status is rejected outright.
    # This is the defense-in-depth check described in docs/architecture/phase0.md.
    if user is None or user.tenant_id != payload.tenant_id or not user.is_active:
        raise credentials_error

    return user
