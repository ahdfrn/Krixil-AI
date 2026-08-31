import uuid

from sqlalchemy import Boolean, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        # Email is unique per tenant, not globally — tenants are isolated workspaces, so the
        # same email can legitimately register as the owner of two different tenants.
        UniqueConstraint("tenant_id", "email", name="uq_users_tenant_id_email"),
        Index("ix_users_tenant_id_id", "tenant_id", "id"),
    )

    # No standalone index: the composite (tenant_id, id) index below already covers
    # tenant_id-only lookups via its leftmost-prefix.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # totp_secret is set as soon as 2FA setup starts, before it's confirmed — totp_enabled only
    # flips true once the user proves possession with a real code (POST /auth/2fa/confirm).
    totp_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
