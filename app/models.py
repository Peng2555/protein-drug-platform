"""Database models."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    jobs: Mapped[list["Job"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    batches: Mapped[list["Batch"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(128))
    batch_type: Mapped[str] = mapped_column(String(32), default="vhh_panel")

    target_name: Mapped[str] = mapped_column(String(128))
    target_chain_id: Mapped[str] = mapped_column(String(16), default="A")
    target_sequence: Mapped[str] = mapped_column(Text)
    heavy_chain_id: Mapped[str] = mapped_column(String(16), default="H")
    heavy_chain_count: Mapped[int] = mapped_column(Integer)

    use_msa_server: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(back_populates="batches")
    jobs: Mapped[list["Job"]] = relationship(back_populates="batch")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("batches.id"), nullable=True, index=True)
    heavy_chain_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    engine: Mapped[str] = mapped_column(String(32), default="boltz2")
    status: Mapped[str] = mapped_column(String(16), default=JobStatus.queued.value, index=True)

    fasta_text: Mapped[str] = mapped_column(Text)
    sequence_hash: Mapped[str] = mapped_column(String(64), index=True)
    chains_json: Mapped[dict] = mapped_column(JSON)  # {chain_id: length}
    total_length: Mapped[int] = mapped_column(Integer)

    use_msa_server: Mapped[bool] = mapped_column(Boolean, default=True)
    params_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    iptm: Mapped[float | None] = mapped_column(Float, nullable=True)
    ptm: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    complex_plddt: Mapped[float | None] = mapped_column(Float, nullable=True)
    dockq: Mapped[float | None] = mapped_column(Float, nullable=True)
    pdockq: Mapped[float | None] = mapped_column(Float, nullable=True)
    pdockq2: Mapped[float | None] = mapped_column(Float, nullable=True)
    runtime_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    work_dir: Mapped[str | None] = mapped_column(String(512), nullable=True)
    structure_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    parent_job_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("jobs.id"), nullable=True, index=True)
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    results_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="jobs")
    batch: Mapped["Batch | None"] = relationship(back_populates="jobs")
