import uuid

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID


class Document(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "documents"
    __table_args__ = (Index("ix_documents_tenant_id_id", "tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # "processing" | "ready" | "failed"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # "upload" | "conversation" — conversation-sourced documents have no real file behind them
    # (see app/rag/conversation_ingest.py), so storage_key is a sentinel, not a real MinIO key.
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="upload")
    # Soft reference, deliberately not a foreign key — the background task that creates
    # conversation-sourced documents isn't guaranteed by FastAPI to run after the triggering
    # request's own session has committed the Conversation row (a real FK here hit exactly this
    # race for app/models/user_memory.py's equivalent field; same fix applied preemptively here).
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)
