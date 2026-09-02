"""agent_runs.runtime + external_run_id (Hermes runtime support)

Revision ID: 0018_agent_run_runtime
Revises: 0017_swarm_task_dependencies
Create Date: 2026-09-03

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_agent_run_runtime"
down_revision: str | None = "0017_swarm_task_dependencies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_runs",
        sa.Column("runtime", sa.String(20), nullable=False, server_default="native"),
    )
    op.add_column("agent_runs", sa.Column("external_run_id", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "external_run_id")
    op.drop_column("agent_runs", "runtime")
