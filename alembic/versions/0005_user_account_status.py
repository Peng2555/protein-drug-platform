"""用户账号状态与登录令牌版本。

Revision ID: 0005_user_account_status
Revises: 0004_chain_nucleotide
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0005_user_account_status"
down_revision = "0004_chain_nucleotide"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("account_status", sa.String(length=16), nullable=False, server_default="active"),
    )
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.execute(
        "UPDATE users SET account_status = CASE WHEN is_active THEN 'active' ELSE 'pending' END"
    )


def downgrade() -> None:
    op.drop_column("users", "token_version")
    op.drop_column("users", "account_status")
