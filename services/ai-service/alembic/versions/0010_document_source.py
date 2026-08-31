"""documents.source + source_conversation_id

Revision ID: 0010_document_source
Revises: 0009_user_memories
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.types import GUID

revision: str = "0010_document_source"
down_revision: str | None = "0009_user_memories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("source", sa.String(20), nullable=False, server_default="upload"),
    )
    # Deliberately no foreign key — see app/models/document.py for why.
    op.add_column("documents", sa.Column("source_conversation_id", GUID(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "source_conversation_id")
    op.drop_column("documents", "source")
