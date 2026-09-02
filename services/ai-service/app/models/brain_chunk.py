import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import get_settings
from app.db.base import Base, TimestampMixin, UUIDPKMixin
from app.db.types import GUID
from app.db.vector_type import EmbeddingVector


class BrainChunk(UUIDPKMixin, TimestampMixin, Base):
    """One real, embedded chunk of a real file's real content — Project Brain's searchable index
    (PRD §13's "Vector Index"/"Semantic Search"). Chunked via the same character-based
    app/rag/chunker.py's chunk_text() the document-upload RAG pipeline already uses (real
    settings.rag_chunk_size/rag_chunk_overlap, not a code-aware split — a chunk can span more
    than one function, or cut one mid-body); embedded via whichever ModelProvider is active, same
    as every other embeddings() call in this app. See app/brain/service.py."""

    __tablename__ = "brain_chunks"
    __table_args__ = (Index("ix_brain_chunks_tenant_id_id", "tenant_id", "id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    index_run_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("brain_index_runs.id", ondelete="CASCADE"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Guessed from the file extension (app/brain/symbols.py's _guess_language) — cosmetic, shown
    # in search results, not used to gate indexing (every decodable-as-text file gets indexed
    # regardless of whether its language is recognized).
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        EmbeddingVector(get_settings().embedding_dimension), nullable=False
    )
