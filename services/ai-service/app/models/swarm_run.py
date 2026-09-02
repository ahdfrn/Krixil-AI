import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class SwarmRun(UUIDPKMixin, TimestampMixin, Base):
    """A real coordinator for a Multi-Agent Swarm (PRD §27) — decomposes one goal into several
    real, independent AgentRuns (app/models/agent_run.py, linked back via their own
    swarm_run_id), runs them concurrently, then makes one more real model call to synthesize
    their actual final_responses into a combined report. Not a fabricated roster of named
    specialist agents — every child is the exact same general agent loop, differentiated only by
    its own real goal text (see app/agents/swarm.py)."""

    __tablename__ = "swarm_runs"
    __table_args__ = (Index("ix_swarm_runs_tenant_id_id", "tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    # "running" (decomposing or children in flight) | "completed" | "failed" (decomposition
    # produced fewer than 2 real sub-tasks, or every child failed) — a real, honest terminal
    # state, never a fabricated success.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    model_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # The real number of sub-tasks decomposition actually produced — not a target/requested count.
    subtask_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # The real, final model call over every child's actual final_response — None until every
    # child has reached a terminal state and synthesis has actually run.
    synthesis: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
