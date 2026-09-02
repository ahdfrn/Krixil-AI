"""swarm_runs table

Revision ID: 0013_swarm_runs
Revises: 0012_agent_run_model_id
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.types import GUID

revision: str = "0013_swarm_runs"
down_revision: str | None = "0012_agent_run_model_id"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "swarm_runs",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", GUID(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("model_id", sa.String(200), nullable=True),
        sa.Column("subtask_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("synthesis", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_swarm_runs_tenant_id_id", "swarm_runs", ["tenant_id", "id"])

    op.add_column("agent_runs", sa.Column("swarm_run_id", GUID(), nullable=True))
    op.create_foreign_key(
        "fk_agent_runs_swarm_run_id_swarm_runs",
        "agent_runs",
        "swarm_runs",
        ["swarm_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_agent_runs_swarm_run_id_swarm_runs", "agent_runs", type_="foreignkey")
    op.drop_column("agent_runs", "swarm_run_id")
    op.drop_index("ix_swarm_runs_tenant_id_id", table_name="swarm_runs")
    op.drop_table("swarm_runs")
