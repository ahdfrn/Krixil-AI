import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class AgentRun(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_runs"
    __table_args__ = (Index("ix_agent_runs_tenant_id_id", "tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    # "running" | "completed" | "stopped" | "waiting_approval" | "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    max_tool_calls: Mapped[int] = mapped_column(Integer, nullable=False)
    max_execution_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    step_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    final_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending_execution_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("tool_executions.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
