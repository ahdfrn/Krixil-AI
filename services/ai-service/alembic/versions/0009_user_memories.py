"""user_memories table + users.memory_enabled

Revision ID: 0009_user_memories
Revises: 0008_ollama_embedding_dim
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.types import GUID

revision: str = "0009_user_memories"
down_revision: str | None = "0008_ollama_embedding_dim"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("memory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "user_memories",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "user_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("content", sa.Text(), nullable=False),
        # Traceability only, deliberately not a foreign key — see app/models/user_memory.py for
        # why (a real timing race with the background extraction task that creates these rows).
        sa.Column("source_conversation_id", GUID(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_user_memories_tenant_id_user_id", "user_memories", ["tenant_id", "user_id"]
    )


def downgrade() -> None:
    op.drop_table("user_memories")
    op.drop_column("users", "memory_enabled")
