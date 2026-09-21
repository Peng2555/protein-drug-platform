"""抗体改造项目的数据模型。

模型保持面向业务：项目、候选抗体、不可变序列版本、样品、实验与溯源。
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def uuid4_str() -> str:
    return str(uuid.uuid4())


class ProjectStatus(str, enum.Enum):
    initiated = "initiated"
    design = "design"
    computation = "computation"
    synthesis = "synthesis"
    experiment = "experiment"
    completed = "completed"
    paused = "paused"
    archived = "archived"


class ProjectRole(str, enum.Enum):
    owner = "owner"
    editor = "editor"
    viewer = "viewer"


class AntibodyType(str, enum.Enum):
    igg = "igg"
    vhh = "vhh"


class AntibodyCategory(str, enum.Enum):
    rm = "RM"
    rn = "RN"
    rl = "RL"


class VersionStatus(str, enum.Enum):
    draft = "draft"
    locked = "locked"
    tested = "tested"
    rejected = "rejected"


class AntibodyProject(Base):
    __tablename__ = "antibody_projects"
    __table_args__ = (
        UniqueConstraint("owner_id", "project_code", name="uq_antibody_projects_owner_code"),
        Index("ix_antibody_projects_owner_status", "owner_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    project_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    target_name: Mapped[str] = mapped_column(String(160), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(24), default=ProjectStatus.initiated.value, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProjectMember(Base):
    __tablename__ = "antibody_project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_antibody_project_member"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_projects.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(16), default=ProjectRole.viewer.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AntibodyCandidate(Base):
    __tablename__ = "antibody_candidates"
    __table_args__ = (
        UniqueConstraint("project_id", "candidate_code", name="uq_antibody_candidate_code"),
        CheckConstraint(
            "antibody_category IS NULL OR antibody_category IN ('RM', 'RN', 'RL')",
            name="ck_antibody_candidate_category",
        ),
        Index("ix_antibody_candidates_project_status", "project_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_projects.id", ondelete="RESTRICT"), index=True
    )
    candidate_code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(160))
    antibody_category: Mapped[str | None] = mapped_column(String(2), nullable=True)
    antibody_type: Mapped[str] = mapped_column(String(16))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active", index=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    archived_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AntibodyVersion(Base):
    __tablename__ = "antibody_versions"
    __table_args__ = (
        UniqueConstraint("candidate_id", "version_code", name="uq_antibody_version_code"),
        UniqueConstraint(
            "candidate_id", "version_number", name="uq_antibody_version_number"
        ),
        CheckConstraint(
            "primary_parent_id IS NULL OR primary_parent_id <> id",
            name="ck_antibody_version_not_own_parent",
        ),
        CheckConstraint("version_number >= 0", name="ck_antibody_version_number_positive"),
        Index("ix_antibody_versions_candidate_status", "candidate_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    candidate_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_candidates.id", ondelete="RESTRICT"), index=True
    )
    primary_parent_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="RESTRICT"), nullable=True
    )
    version_code: Mapped[str] = mapped_column(String(32))
    version_number: Mapped[int] = mapped_column(Integer)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=VersionStatus.draft.value, index=True
    )
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    locked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AntibodyVersionChain(Base):
    __tablename__ = "antibody_version_chains"
    __table_args__ = (
        UniqueConstraint("version_id", "chain_role", name="uq_antibody_version_chain_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="CASCADE"), index=True
    )
    chain_role: Mapped[str] = mapped_column(String(16))
    chain_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    variable_sequence: Mapped[str] = mapped_column(Text)
    full_sequence: Mapped[str | None] = mapped_column(Text, nullable=True)
    nucleotide_sequence: Mapped[str | None] = mapped_column(Text, nullable=True)
    sequence_hash: Mapped[str] = mapped_column(String(64), index=True)
    numbering_scheme: Mapped[str] = mapped_column(String(16), default="kabat")
    annotation_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    annotation_tool: Mapped[str | None] = mapped_column(String(64), nullable=True)
    annotation_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class VersionMutation(Base):
    __tablename__ = "antibody_version_mutations"
    __table_args__ = (
        Index("ix_antibody_mutations_version_chain", "version_id", "chain_role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="CASCADE"), index=True
    )
    parent_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="RESTRICT")
    )
    chain_role: Mapped[str] = mapped_column(String(16))
    mutation_type: Mapped[str] = mapped_column(String(16))
    sequence_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    numbering_label: Mapped[str | None] = mapped_column(String(24), nullable=True)
    kabat_label: Mapped[str | None] = mapped_column(String(24), nullable=True)
    from_aa: Mapped[str | None] = mapped_column(String(8), nullable=True)
    to_aa: Mapped[str | None] = mapped_column(String(8), nullable=True)
    region: Mapped[str | None] = mapped_column(String(24), nullable=True)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_effect: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SampleBatch(Base):
    __tablename__ = "antibody_sample_batches"
    __table_args__ = (
        UniqueConstraint("version_id", "batch_code", name="uq_antibody_sample_batch_code"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="RESTRICT"), index=True
    )
    batch_code: Mapped[str] = mapped_column(String(64))
    expression_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purification_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    concentration_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    concentration_unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    purity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    storage_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    operator_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ExperimentRecord(Base):
    __tablename__ = "antibody_experiments"
    __table_args__ = (
        Index("ix_antibody_experiments_version_type", "version_id", "experiment_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_projects.id", ondelete="RESTRICT"), index=True
    )
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="RESTRICT"), index=True
    )
    sample_batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("antibody_sample_batches.id", ondelete="RESTRICT"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(160))
    experiment_type: Mapped[str] = mapped_column(String(32), index=True)
    experiment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    operator_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    conditions_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ExperimentMeasurement(Base):
    __tablename__ = "antibody_experiment_measurements"
    __table_args__ = (
        Index("ix_antibody_measurements_experiment_metric", "experiment_id", "metric_name"),
        CheckConstraint(
            "value_numeric IS NOT NULL OR value_text IS NOT NULL",
            name="ck_antibody_measurement_has_value",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    experiment_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_experiments.id", ondelete="CASCADE"), index=True
    )
    metric_name: Mapped[str] = mapped_column(String(64))
    value_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    value_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    qualifier: Mapped[str | None] = mapped_column(String(16), nullable=True)
    replicate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectJobLink(Base):
    __tablename__ = "antibody_project_job_links"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "original_job_id", name="uq_antibody_version_original_job"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_projects.id", ondelete="RESTRICT"), index=True
    )
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="RESTRICT"), index=True
    )
    job_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    original_job_id: Mapped[str] = mapped_column(String(36))
    engine: Mapped[str] = mapped_column(String(32))
    purpose: Mapped[str | None] = mapped_column(String(160), nullable=True)
    input_sequence_hash: Mapped[str] = mapped_column(String(64))
    params_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    linked_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ProjectArtifact(Base):
    __tablename__ = "antibody_project_artifacts"
    __table_args__ = (
        UniqueConstraint("project_id", "storage_path", name="uq_antibody_artifact_path"),
        Index("ix_antibody_artifacts_project_category", "project_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_projects.id", ondelete="RESTRICT"), index=True
    )
    version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("antibody_versions.id", ondelete="RESTRICT"), nullable=True
    )
    sample_batch_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("antibody_sample_batches.id", ondelete="RESTRICT"), nullable=True
    )
    experiment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("antibody_experiments.id", ondelete="RESTRICT"), nullable=True
    )
    job_link_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("antibody_project_job_links.id", ondelete="RESTRICT"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(32))
    file_name: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    mime_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uploaded_by: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="RESTRICT")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AuditEvent(Base):
    __tablename__ = "antibody_audit_events"
    __table_args__ = (
        Index("ix_antibody_audit_project_created", "project_id", "created_at"),
        Index("ix_antibody_audit_entity", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uuid4_str)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("antibody_projects.id", ondelete="RESTRICT"), index=True
    )
    entity_type: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[str] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(32))
    actor_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    before_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
