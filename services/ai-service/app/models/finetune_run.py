import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class FinetuneRun(UUIDPKMixin, TimestampMixin, Base):
    """One attempt of the autonomous fine-tuning pipeline (training/, a separate native-Windows
    project — see docs/architecture/learning-and-memory.md Phase 3). Rows are created here by the
    api service (a "requested" row for a manual trigger, or training/ reporting a run it started
    on its own) and updated via POST /finetune/report once training/ finishes — this table is
    what makes "runs on its own" visible rather than a black box, surfaced in Settings.
    """

    __tablename__ = "finetune_runs"
    __table_args__ = (Index("ix_finetune_runs_tenant_id_id", "tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # "requested" | "running" | "promoted" | "discarded" | "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="requested")
    example_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    promoted_tag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    eval_pass_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    eval_fail_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regression: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
