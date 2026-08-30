import uuid

from sqlalchemy import JSON, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class Role(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "roles"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_id_name"),
        Index("ix_roles_tenant_id_id", "tenant_id", "id"),
    )

    # No standalone index: the composite (tenant_id, id) index below already covers
    # tenant_id-only lookups via its leftmost-prefix.
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # List of permission strings, e.g. ["*"] for owner. Enforced by later phases' RBAC checks.
    permissions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
