import uuid

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class SwarmTaskDependency(UUIDPKMixin, TimestampMixin, Base):
    """One real edge in a Multi-Agent Swarm's dependency graph (PRD §27) — `agent_run_id` (a real
    child AgentRun) must wait for `depends_on_agent_run_id` (another real child of the same
    SwarmRun) to finish before it starts. A dependency is genuinely many-to-many (one sub-task can
    gate several dependents; a dependent can have several prerequisites), so this is a real edge
    table, own `tenant_id` for direct query scoping — same shape as AgentStep, not a JSON column
    on AgentRun. See app/agents/swarm.py."""

    __tablename__ = "swarm_task_dependencies"
    __table_args__ = (
        Index("ix_swarm_task_dependencies_tenant_id_id", "tenant_id", "id"),
        UniqueConstraint(
            "agent_run_id", "depends_on_agent_run_id", name="uq_swarm_task_dependencies_edge"
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    depends_on_agent_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
