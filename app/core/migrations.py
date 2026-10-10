"""Lightweight schema migrations (add columns / tables on startup)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text

from app.core.database import engine
from app.core.config import settings


def run_migrations() -> None:
    """升级数据库，同时兼容接入 Alembic 之前的旧数据库。"""
    initial_tables = set(inspect(engine).get_table_names())
    if {"users", "jobs"}.issubset(initial_tables):
        _run_legacy_column_migrations()

    root = Path(__file__).resolve().parents[2]
    alembic_config = Config(str(root / "alembic.ini"))
    command.upgrade(alembic_config, "head")

    # 极旧数据库可能缺少历史列；保留这一段兼容补丁，确认全部环境升级后再移除。
    _run_legacy_column_migrations()


def _run_legacy_column_migrations() -> None:
    insp = inspect(engine)
    dialect = engine.dialect.name

    if not insp.has_table("batches"):
        from app.core.database import Base
        from app.core.models import Batch  # noqa: F401

        Batch.__table__.create(bind=engine, checkfirst=True)

    if insp.has_table("jobs"):
        cols = {c["name"] for c in insp.get_columns("jobs")}
        with engine.begin() as conn:
            if "batch_id" not in cols:
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN batch_id VARCHAR(36)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_batch_id ON jobs (batch_id)"))
                else:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN batch_id VARCHAR(36)"))
            if "heavy_chain_id" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN heavy_chain_id VARCHAR(64)"))
            if "parent_job_id" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN parent_job_id VARCHAR(36)"))
                if dialect == "postgresql":
                    conn.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_parent_job_id ON jobs (parent_job_id)"))
            if "stage" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN stage VARCHAR(32)"))
            if "results_json" not in cols:
                if dialect == "postgresql":
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN results_json JSONB"))
                else:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN results_json JSON"))
            if "dockq" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN dockq FLOAT"))
            if "pdockq" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN pdockq FLOAT"))
            if "pdockq2" not in cols:
                conn.execute(text("ALTER TABLE jobs ADD COLUMN pdockq2 FLOAT"))

    if insp.has_table("users"):
        cols = {c["name"] for c in insp.get_columns("users")}
        with engine.begin() as conn:
            if "is_admin" not in cols:
                default_admin = "0" if dialect == "sqlite" else "FALSE"
                conn.execute(text(f"ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT {default_admin}"))
                conn.execute(
                    text("UPDATE users SET is_admin = :val WHERE username = :name"),
                    {"val": True, "name": settings.admin_username},
                )
