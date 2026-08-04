"""Lightweight schema migrations (add columns / tables on startup)."""

from __future__ import annotations

from sqlalchemy import inspect, text

from app.database import engine


def run_migrations() -> None:
    insp = inspect(engine)
    dialect = engine.dialect.name

    if not insp.has_table("batches"):
        from app.database import Base
        from app.models import Batch  # noqa: F401

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
