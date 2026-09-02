"""Persist project scope across approval and resume."""

import sqlalchemy as sa

from alembic import op

revision = "0019_project_scope"
down_revision = "0018_agent_run_runtime"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("agent_runs", "tool_executions"):
        op.add_column(table, sa.Column("workspace_root", sa.String(1000), nullable=True))


def downgrade():
    for table in ("tool_executions", "agent_runs"):
        op.drop_column(table, "workspace_root")
