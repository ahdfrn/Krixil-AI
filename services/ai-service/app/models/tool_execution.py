import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class ToolExecution(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tool_executions"
    __table_args__ = (Index("ix_tool_executions_tenant_id_id", "tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    workspace_root: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), nullable=False)
    # "pending_approval" | "running" | "completed" | "failed" | "rejected" | "blocked"
    # ("blocked" — a real, hard-coded BLOCK-tier match, app/tools/risk_rules.py — never offered
    # for approval at all, unlike "rejected" which a human actively declined.)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    input: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
