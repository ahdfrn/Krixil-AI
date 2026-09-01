"""agent_run model_id

Revision ID: 0012_agent_run_model_id
Revises: 0011_finetune_runs
Create Date: 2026-09-01

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0012_agent_run_model_id"
down_revision: str | None = "0011_finetune_runs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("model_id", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "model_id")
