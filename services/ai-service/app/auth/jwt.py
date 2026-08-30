import uuid
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()


class TokenPayload:
    def __init__(self, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str):
        self.user_id = user_id
        self.tenant_id = tenant_id
        self.role = role


def create_access_token(*, user_id: uuid.UUID, tenant_id: uuid.UUID, role: str) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> TokenPayload:
    """Raises jose.JWTError on invalid/expired/malformed tokens — callers turn that into a 401."""
    payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    user_id = payload.get("sub")
    tenant_id = payload.get("tenant_id")
    role = payload.get("role")
    if not user_id or not tenant_id or not role:
        raise JWTError("Token payload missing required claims")
    return TokenPayload(user_id=uuid.UUID(user_id), tenant_id=uuid.UUID(tenant_id), role=role)
