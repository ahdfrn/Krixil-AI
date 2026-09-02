"""mcp_servers table

Revision ID: 0015_mcp_servers
Revises: 0014_brain
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.db.types import GUID

revision: str = "0015_mcp_servers"
down_revision: str | None = "0014_brain"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_servers",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column(
            "tenant_id", GUID(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("command", sa.String(500), nullable=False),
        sa.Column("args", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("env", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_mcp_servers_tenant_id_id", "mcp_servers", ["tenant_id", "id"])
    op.create_unique_constraint(
        "uq_mcp_servers_tenant_id_name", "mcp_servers", ["tenant_id", "name"]
    )


def downgrade() -> None:
    op.drop_table("mcp_servers")
