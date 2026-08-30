import uuid

from sqlalchemy import ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID
from app.db.vector_type import EmbeddingVector


class DocumentChunk(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_tenant_id_id", "tenant_id", "id"),
        Index("ix_document_chunks_document_id_chunk_index", "document_id", "chunk_index"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        EmbeddingVector(get_settings().embedding_dimension), nullable=False
    )
