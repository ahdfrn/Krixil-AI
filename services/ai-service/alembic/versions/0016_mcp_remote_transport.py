"""mcp remote transport (sse/http)

Revision ID: 0016_mcp_remote_transport
Revises: 0015_mcp_servers
Create Date: 2026-09-02

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0016_mcp_remote_transport"
down_revision: str | None = "0015_mcp_servers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "mcp_servers",
        sa.Column("transport", sa.String(20), nullable=False, server_default="stdio"),
    )
    op.alter_column("mcp_servers", "command", existing_type=sa.String(500), nullable=True)
    op.add_column("mcp_servers", sa.Column("url", sa.String(2000), nullable=True))
    op.add_column(
        "mcp_servers", sa.Column("headers", sa.JSON(), nullable=False, server_default="{}")
    )


def downgrade() -> None:
    op.drop_column("mcp_servers", "headers")
    op.drop_column("mcp_servers", "url")
    op.alter_column("mcp_servers", "command", existing_type=sa.String(500), nullable=False)
    op.drop_column("mcp_servers", "transport")
