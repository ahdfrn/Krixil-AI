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
    # "running" | "completed" | "stopped" | "waiting_approval" | "failed" | "cancelled"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    # None/"auto" mean "provider's configured default" (see AgentRunRequest.model). Persisted
    # (unlike before) so a run that pauses on approval can resume on the same model it started
    # on — the background task that resumes it (app/tools/service.py's approve path) has no
    # access to the original request payload, only this row.
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
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
    # Set only for a run created as one real child of a Multi-Agent Swarm (app/agents/swarm.py) —
    # None for every other run. Lets `kirxil swarm`'s status poll show real per-child progress
    # without a separate join table.
    swarm_run_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("swarm_runs.id", ondelete="SET NULL"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
