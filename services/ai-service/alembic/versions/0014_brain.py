"""brain_index_runs and brain_chunks tables

Revision ID: 0014_brain
Revises: 0013_swarm_runs
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.config import get_settings
from app.db.types import GUID
from app.db.vector_type import EmbeddingVector

revision: str = "0014_brain"
down_revision: str | None = "0013_swarm_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    embedding_dim = get_settings().embedding_dimension

    op.create_table(
        "brain_index_runs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("directory", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("file_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("symbol_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_brain_index_runs_tenant_id_id", "brain_index_runs", ["tenant_id", "id"]
    )

    op.create_table(
        "brain_chunks",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "index_run_id",
            GUID(),
            sa.ForeignKey("brain_index_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("language", sa.String(50), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", EmbeddingVector(embedding_dim), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_brain_chunks_tenant_id_id", "brain_chunks", ["tenant_id", "id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "CREATE INDEX ix_brain_chunks_embedding_hnsw ON brain_chunks "
            "USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.drop_table("brain_chunks")
    op.drop_table("brain_index_runs")
