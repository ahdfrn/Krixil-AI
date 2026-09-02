"""swarm_task_dependencies table + agent_runs.original_goal

Revision ID: 0017_swarm_task_dependencies
Revises: 0016_mcp_remote_transport
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.types import GUID

revision: str = "0017_swarm_task_dependencies"
down_revision: str | None = "0016_mcp_remote_transport"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "swarm_task_dependencies",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "agent_run_id",
            GUID(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "depends_on_agent_run_id",
            GUID(),
            sa.ForeignKey("agent_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index(
        "ix_swarm_task_dependencies_tenant_id_id", "swarm_task_dependencies", ["tenant_id", "id"]
    )
    op.create_unique_constraint(
        "uq_swarm_task_dependencies_edge",
        "swarm_task_dependencies",
        ["agent_run_id", "depends_on_agent_run_id"],
    )

    op.add_column("agent_runs", sa.Column("original_goal", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "original_goal")
    op.drop_constraint(
        "uq_swarm_task_dependencies_edge", "swarm_task_dependencies", type_="unique"
    )
    op.drop_index("ix_swarm_task_dependencies_tenant_id_id", table_name="swarm_task_dependencies")
    op.drop_table("swarm_task_dependencies")
