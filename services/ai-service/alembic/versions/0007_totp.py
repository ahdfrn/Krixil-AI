"""2FA (TOTP) columns on users

Revision ID: 0007_totp
Revises: 0006_evaluations
Create Date: 2026-08-31

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_totp"
down_revision: str | None = "0006_evaluations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret", sa.String(64), nullable=True))
    op.add_column(
        "users",
        sa.Column("totp_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret")
