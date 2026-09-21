"""为现有 users、batches、jobs 建立无损基线。

Revision ID: 0001_legacy_schema
Revises:
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_legacy_schema"
down_revision = None
branch_labels = None
depends_on = None


def _index(name: str, table: str, columns: list[str], *, unique: bool = False) -> None:
    bind = op.get_bind()
    existing = {item["name"] for item in sa.inspect(bind).get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=unique)


def upgrade() -> None:
    """已有表保持原样；仅在空数据库中创建平台原有三张表。"""
    bind = op.get_bind()
    tables = set(sa.inspect(bind).get_table_names())

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("email", sa.String(255), nullable=True),
            sa.Column("password_hash", sa.String(255), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False),
            sa.Column("is_admin", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email"),
        )
        _index("ix_users_username", "users", ["username"], unique=True)

    tables = set(sa.inspect(bind).get_table_names())
    if "batches" not in tables:
        op.create_table(
            "batches",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("name", sa.String(128), nullable=False),
            sa.Column("batch_type", sa.String(32), nullable=False),
            sa.Column("target_name", sa.String(128), nullable=False),
            sa.Column("target_chain_id", sa.String(16), nullable=False),
            sa.Column("target_sequence", sa.Text(), nullable=False),
            sa.Column("heavy_chain_id", sa.String(16), nullable=False),
            sa.Column("heavy_chain_count", sa.Integer(), nullable=False),
            sa.Column("use_msa_server", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        _index("ix_batches_user_id", "batches", ["user_id"])

    tables = set(sa.inspect(bind).get_table_names())
    if "jobs" not in tables:
        op.create_table(
            "jobs",
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("user_id", sa.String(36), nullable=False),
            sa.Column("batch_id", sa.String(36), nullable=True),
            sa.Column("heavy_chain_id", sa.String(64), nullable=True),
            sa.Column("name", sa.String(128), nullable=True),
            sa.Column("engine", sa.String(32), nullable=False),
            sa.Column("status", sa.String(16), nullable=False),
            sa.Column("fasta_text", sa.Text(), nullable=False),
            sa.Column("sequence_hash", sa.String(64), nullable=False),
            sa.Column("chains_json", sa.JSON(), nullable=False),
            sa.Column("total_length", sa.Integer(), nullable=False),
            sa.Column("use_msa_server", sa.Boolean(), nullable=False),
            sa.Column("params_json", sa.JSON(), nullable=True),
            sa.Column("iptm", sa.Float(), nullable=True),
            sa.Column("ptm", sa.Float(), nullable=True),
            sa.Column("confidence_score", sa.Float(), nullable=True),
            sa.Column("complex_plddt", sa.Float(), nullable=True),
            sa.Column("dockq", sa.Float(), nullable=True),
            sa.Column("pdockq", sa.Float(), nullable=True),
            sa.Column("pdockq2", sa.Float(), nullable=True),
            sa.Column("runtime_seconds", sa.Float(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("work_dir", sa.String(512), nullable=True),
            sa.Column("structure_path", sa.String(512), nullable=True),
            sa.Column("celery_task_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("parent_job_id", sa.String(36), nullable=True),
            sa.Column("stage", sa.String(32), nullable=True),
            sa.Column("results_json", sa.JSON(), nullable=True),
            sa.ForeignKeyConstraint(["batch_id"], ["batches.id"]),
            sa.ForeignKeyConstraint(["parent_job_id"], ["jobs.id"]),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
        for name, columns in (
            ("ix_jobs_user_id", ["user_id"]),
            ("ix_jobs_batch_id", ["batch_id"]),
            ("ix_jobs_status", ["status"]),
            ("ix_jobs_sequence_hash", ["sequence_hash"]),
            ("ix_jobs_parent_job_id", ["parent_job_id"]),
        ):
            _index(name, "jobs", columns)


def downgrade() -> None:
    # 基线可能对应已有生产数据，禁止自动删除原平台表。
    pass
