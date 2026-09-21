"""抗体改造项目 API 数据契约。"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    project_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    target_name: str = Field(min_length=1, max_length=160)
    description: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    target_name: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = None
    status: str | None = None


class ProjectOut(BaseModel):
    id: str
    owner_id: str
    project_code: str
    name: str
    target_name: str
    description: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    model_config = {"from_attributes": True}


class ProjectMemberCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    role: str = Field(pattern="^(editor|viewer)$")


class ProjectMemberUpdate(BaseModel):
    role: str = Field(pattern="^(editor|viewer)$")


class ProjectMemberOut(BaseModel):
    id: str
    user_id: str
    username: str
    role: str
    created_at: datetime


class VersionChainInput(BaseModel):
    chain_role: str = Field(min_length=1, max_length=16)
    variable_sequence: str = Field(min_length=1)
    full_sequence: str | None = None
    nucleotide_sequence: str | None = None
    chain_name: str | None = Field(default=None, max_length=64)


class VersionChainOut(BaseModel):
    id: str
    chain_role: str
    chain_name: str | None
    variable_sequence: str
    full_sequence: str | None
    nucleotide_sequence: str | None = None
    sequence_hash: str
    numbering_scheme: str
    annotation_json: dict | None
    annotation_tool: str | None
    annotation_version: str | None

    model_config = {"from_attributes": True}


class CandidateCreate(BaseModel):
    candidate_code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=160)
    antibody_category: str = Field(pattern="^(RM|RN|RL)$")
    antibody_type: str = Field(pattern="^(igg|vhh)$")
    description: str | None = None
    wt_name: str | None = Field(default="母本抗体", max_length=160)
    chains: list[VersionChainInput] = Field(min_length=1, max_length=4)


class CandidateOut(BaseModel):
    id: str
    project_id: str
    candidate_code: str
    name: str
    antibody_category: str | None
    antibody_type: str
    description: str | None
    status: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    model_config = {"from_attributes": True}


class CandidateCategoryUpdate(BaseModel):
    antibody_category: str = Field(pattern="^(RM|RN|RL)$")


class VersionCreate(BaseModel):
    parent_version_id: str
    name: str | None = Field(default=None, max_length=160)
    purpose: str | None = None
    rationale: str | None = None
    evidence: str | None = None
    chains: list[VersionChainInput] = Field(min_length=1, max_length=4)


class VersionImportItem(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    chains: list[VersionChainInput] = Field(min_length=1, max_length=4)


class VersionImportRequest(BaseModel):
    parent_version_id: str
    items: list[VersionImportItem] = Field(min_length=1, max_length=200)


class VersionLockDrafts(BaseModel):
    round: str | None = Field(default=None, max_length=16)


class VersionUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    purpose: str | None = None
    rationale: str | None = None
    evidence: str | None = None
    chains: list[VersionChainInput] | None = Field(default=None, min_length=1, max_length=4)


class MutationOut(BaseModel):
    id: str
    chain_role: str
    mutation_type: str
    sequence_position: int | None
    numbering_label: str | None
    kabat_label: str | None
    from_aa: str | None
    to_aa: str | None
    region: str | None
    rationale: str | None
    expected_effect: str | None
    evidence: str | None

    model_config = {"from_attributes": True}


class MutationUpdate(BaseModel):
    rationale: str | None = None
    expected_effect: str | None = None
    evidence: str | None = None


class VersionOut(BaseModel):
    id: str
    candidate_id: str
    primary_parent_id: str | None
    version_code: str
    version_number: int
    name: str | None
    status: str
    purpose: str | None
    rationale: str | None
    evidence: str | None
    sequence_hash: str
    created_by: str
    created_at: datetime
    updated_at: datetime
    locked_at: datetime | None
    chains: list[VersionChainOut] = Field(default_factory=list)
    mutations: list[MutationOut] = Field(default_factory=list)


class SequenceDifferenceOut(BaseModel):
    chain_role: str
    mutation_type: str
    sequence_position: int | None
    from_aa: str | None
    to_aa: str | None


class VersionComparisonOut(BaseModel):
    base_version: VersionOut
    target_version: VersionOut
    differences: list[SequenceDifferenceOut]


class SampleBatchCreate(BaseModel):
    version_id: str
    batch_code: str = Field(min_length=1, max_length=64)
    expression_date: date | None = None
    purification_date: date | None = None
    concentration_value: float | None = Field(default=None, ge=0)
    concentration_unit: str | None = Field(default=None, max_length=24)
    purity_percent: float | None = Field(default=None, ge=0, le=100)
    storage_location: str | None = Field(default=None, max_length=255)
    notes: str | None = None


class SampleBatchOut(BaseModel):
    id: str
    version_id: str
    batch_code: str
    expression_date: date | None
    purification_date: date | None
    concentration_value: float | None
    concentration_unit: str | None
    purity_percent: float | None
    storage_location: str | None
    operator_id: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeasurementInput(BaseModel):
    metric_name: str = Field(min_length=1, max_length=64)
    value_numeric: float | None = None
    value_text: str | None = Field(default=None, max_length=255)
    unit: str | None = Field(default=None, max_length=32)
    qualifier: str | None = Field(default=None, max_length=16)
    replicate: int | None = Field(default=None, ge=1)
    notes: str | None = None


class MeasurementOut(MeasurementInput):
    id: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ExperimentCreate(BaseModel):
    version_id: str
    sample_batch_id: str | None = None
    title: str = Field(min_length=1, max_length=160)
    experiment_type: str = Field(
        pattern="^(expression|purity|affinity|activity|stability|custom)$"
    )
    experiment_date: date | None = None
    conditions_json: dict | None = None
    result_summary: str | None = None
    notes: str | None = None
    measurements: list[MeasurementInput] = Field(default_factory=list, max_length=200)


class ExperimentOut(BaseModel):
    id: str
    project_id: str
    version_id: str
    sample_batch_id: str | None
    title: str
    experiment_type: str
    experiment_date: date | None
    operator_id: str | None
    conditions_json: dict | None
    result_summary: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
    measurements: list[MeasurementOut] = Field(default_factory=list)


class AffinityPreviewRow(BaseModel):
    excel_row: int
    loading_sample_id: str
    protein_key: str
    antigen: str
    loading_response: float | None = None
    response: float | None = None
    kd_m: float | None = None
    kd_qualifier: str | None = None
    ka: float | None = None
    ka_qualifier: str | None = None
    kdis: float | None = None
    kdis_qualifier: str | None = None
    result: str | None = None
    status: str
    version_id: str | None = None
    version_code: str | None = None
    version_name: str | None = None
    selected: bool = False
    message: str | None = None


class AffinityPreviewOut(BaseModel):
    sheet_name: str
    rows: list[AffinityPreviewRow]
    matched: int
    unmatched: int
    control: int
    duplicate: int


class AffinityImportItem(BaseModel):
    excel_row: int
    version_id: str
    loading_sample_id: str
    protein_key: str | None = None
    antigen: str
    loading_response: float | None = None
    response: float | None = None
    kd_m: float | None = None
    kd_qualifier: str | None = None
    ka: float | None = None
    ka_qualifier: str | None = None
    kdis: float | None = None
    kdis_qualifier: str | None = None
    result: str | None = None


class AffinityImportRequest(BaseModel):
    items: list[AffinityImportItem] = Field(min_length=1, max_length=200)


class JobLinkCreate(BaseModel):
    job_id: str
    version_id: str
    purpose: str | None = Field(default=None, max_length=160)


class JobLinkOut(BaseModel):
    id: str
    project_id: str
    version_id: str
    job_id: str | None
    original_job_id: str
    engine: str
    purpose: str | None
    input_sequence_hash: str
    params_snapshot: dict | None
    result_snapshot: dict | None
    linked_by: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ArtifactOut(BaseModel):
    id: str
    project_id: str
    version_id: str | None
    sample_batch_id: str | None
    experiment_id: str | None
    job_link_id: str | None
    category: str
    file_name: str
    sha256: str
    size_bytes: int
    mime_type: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class AuditEventOut(BaseModel):
    id: str
    project_id: str
    entity_type: str
    entity_id: str
    action: str
    actor_id: str | None
    before_json: dict | None
    after_json: dict | None
    request_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
