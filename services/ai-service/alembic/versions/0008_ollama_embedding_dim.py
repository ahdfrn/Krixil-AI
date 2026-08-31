"""resize document_chunks.embedding for a local Ollama embedding model

Revision ID: 0008_ollama_embedding_dim
Revises: 0007_totp
Create Date: 2026-08-31

"""

from collections.abc import Sequence

from alembic import op
from app.core.config import get_settings

revision: str = "0008_ollama_embedding_dim"
down_revision: str | None = "0007_totp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Switching the embedding model (e.g. to Ollama's nomic-embed-text, 768-dim) means the
    vector(N) column has to be resized. Old vectors are from a different model entirely, not just
    a different size, so they can't be converted — only replaced. Checked the real database before
    writing this: every existing document is a throwaway artifact from live-verification testing,
    none of it real user data, so a truncate-and-reindex is safe here. If this is ever run against
    a database with real documents, re-upload them afterward to get them re-embedded under the new
    model.
    """
    if op.get_bind().dialect.name != "postgresql":
        return

    embedding_dim = get_settings().embedding_dimension

    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("TRUNCATE TABLE document_chunks, documents CASCADE")
    op.execute(f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector({embedding_dim})")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    """Reverses the column shape, not the data — the truncate in upgrade() is inherently lossy,
    same as any migration that resizes a vector column with existing embeddings."""
    if op.get_bind().dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_document_chunks_embedding_hnsw")
    op.execute("TRUNCATE TABLE document_chunks, documents CASCADE")
    op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(1536)")
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )
