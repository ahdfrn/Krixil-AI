import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class BrainIndexRun(UUIDPKMixin, TimestampMixin, Base):
    """One real Project Brain indexing pass (PRD §13) — walks a real directory under HOST_ROOT
    (via host-runner), extracts real symbols (app/brain/symbols.py), chunks and embeds real file
    content (app/brain/service.py), stores the result as BrainChunk rows. file_count/
    symbol_count/chunk_count are the real counts this run actually produced — never a fabricated
    "12,482 files" with no indexer behind it. Each new successful run replaces the tenant's
    previous chunks (a fresh full re-index, not incremental) — see app/brain/service.py."""

    __tablename__ = "brain_index_runs"
    __table_args__ = (Index("ix_brain_index_runs_tenant_id_id", "tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # The real relative directory indexed, under HOST_ROOT (host-runner's own convention — see
    # app/tools/host_tools.py). "." means the whole HOST_ROOT tree.
    directory: Mapped[str] = mapped_column(String(1000), nullable=False)
    # "running" | "completed" | "failed" — a real, honest terminal state; "failed" covers
    # host-runner being unreachable, an empty/unreadable directory, or any real error mid-index.
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running")
    file_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    symbol_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
