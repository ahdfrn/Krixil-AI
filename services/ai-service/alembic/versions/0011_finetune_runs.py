"""finetune_runs table

Revision ID: 0011_finetune_runs
Revises: 0010_document_source
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.types import GUID

revision: str = "0011_finetune_runs"
down_revision: str | None = "0010_document_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "finetune_runs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="requested"),
        sa.Column("example_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("candidate_tag", sa.String(255), nullable=True),
        sa.Column("promoted_tag", sa.String(255), nullable=True),
        sa.Column("eval_pass_count", sa.Integer(), nullable=True),
        sa.Column("eval_fail_count", sa.Integer(), nullable=True),
        sa.Column("regression", sa.Boolean(), nullable=True),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_finetune_runs_tenant_id_id", "finetune_runs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_table("finetune_runs")
