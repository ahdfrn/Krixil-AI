"""documents and document_chunks tables

Revision ID: 0003_documents
Revises: 0002_usage_records
Create Date: 2026-08-30

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.core.config import get_settings
from app.db.types import GUID
from app.db.vector_type import EmbeddingVector

revision: str = "0003_documents"
down_revision: Union[str, None] = "0002_usage_records"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    embedding_dim = get_settings().embedding_dimension

    op.create_table(
        "documents",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="processing"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_documents_tenant_id_id", "documents", ["tenant_id", "id"])

    op.create_table(
        "document_chunks",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "document_id", GUID(), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", EmbeddingVector(embedding_dim), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_document_chunks_tenant_id_id", "document_chunks", ["tenant_id", "id"])
    op.create_index(
        "ix_document_chunks_document_id_chunk_index", "document_chunks", ["document_id", "chunk_index"]
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_document_chunks_embedding_hnsw ON document_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )
        op.execute(
            "CREATE INDEX ix_document_chunks_content_fts ON document_chunks "
            "USING gin (to_tsvector('english', content))"
        )


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("documents")
