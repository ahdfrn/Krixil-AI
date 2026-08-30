import uuid

from sqlalchemy import ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class AgentStep(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "agent_steps"
    __table_args__ = (Index("ix_agent_steps_agent_run_id_step_number", "agent_run_id", "step_number"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    agent_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("agent_runs.id", ondelete="CASCADE"), nullable=False
    )
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # "tool_call" | "observation" | "final_response"
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    tool_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
