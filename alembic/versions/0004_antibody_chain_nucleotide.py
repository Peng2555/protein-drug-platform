"""版本链保存导入用的核酸 CDS。

Revision ID: 0004_chain_nucleotide
Revises: 0003_candidate_category
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_chain_nucleotide"
down_revision = "0003_candidate_category"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("antibody_version_chains") as batch:
        batch.add_column(sa.Column("nucleotide_sequence", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("antibody_version_chains") as batch:
        batch.drop_column("nucleotide_sequence")
