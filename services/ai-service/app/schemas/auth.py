import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    tenant_name: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    tenant_slug: str = Field(min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = Field(default=None, min_length=6, max_length=6)


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    role: str
    is_active: bool
    totp_enabled: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TotpSetupOut(BaseModel):
    secret: str
    otpauth_url: str


class TotpCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class TotpStatusOut(BaseModel):
    totp_enabled: bool


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut
    tenant: TenantOut
