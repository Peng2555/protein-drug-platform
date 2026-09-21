"""增加候选抗体 RM/RN/RL 固定分类。

Revision ID: 0003_candidate_category
Revises: 0002_antibody_projects
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_candidate_category"
down_revision = "0002_antibody_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 允许旧候选暂时为空，由用户在页面补录一次。
    with op.batch_alter_table("antibody_candidates") as batch:
        batch.add_column(sa.Column("antibody_category", sa.String(2), nullable=True))
        batch.create_check_constraint(
            "ck_antibody_candidate_category",
            "antibody_category IS NULL OR antibody_category IN ('RM', 'RN', 'RL')",
        )


def downgrade() -> None:
    with op.batch_alter_table("antibody_candidates") as batch:
        batch.drop_constraint("ck_antibody_candidate_category", type_="check")
        batch.drop_column("antibody_category")
