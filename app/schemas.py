"""Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    email: str | None = None


class UserLogin(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: str
    username: str
    email: str | None
    is_active: bool = True
    is_admin: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class RegisterOut(BaseModel):
    message: str
    username: str
    pending_approval: bool = True


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


class ChainInput(BaseModel):
    id: str
    sequence: str


class EsmFold2Params(BaseModel):
    num_loops: int = Field(default=10, ge=1, le=30)
    num_sampling_steps: int = Field(default=68, ge=1, le=200)
    num_diffusion_samples: int = Field(default=5, ge=1, le=25)
    seed: int = Field(default=0, ge=0, le=2_147_483_647)


class JobCreate(BaseModel):
    fasta: str | None = None
    chains: list[ChainInput] | None = None
    name: str | None = Field(default=None, max_length=128)
    engine: Literal["boltz2", "esmfold2"] = "boltz2"
    use_msa_server: bool = True
    esmfold_params: EsmFold2Params | None = None


class JobOut(BaseModel):
    id: str
    name: str | None
    batch_id: str | None = None
    heavy_chain_id: str | None = None
    parent_job_id: str | None = None
    engine: str
    status: str
    stage: str | None = None
    chains_json: dict
    total_length: int
    use_msa_server: bool
    params_json: dict | None = None
    results_json: dict | None = None
    iptm: float | None
    ptm: float | None
    confidence_score: float | None
    complex_plddt: float | None
    dockq: float | None = None
    pdockq: float | None = None
    pdockq2: float | None = None
    runtime_seconds: float | None
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class MdJobCreate(BaseModel):
    parent_job_id: str | None = None
    structure_path: str | None = None
    name: str | None = Field(default=None, max_length=128)
    production_ns: float | None = Field(default=None, ge=0.1, le=500.0)
    replicas: int | None = Field(default=None, ge=1, le=5)
    antigen_chain: str = Field(default="A", max_length=16)
    binder_chain: str = Field(default="H", max_length=16)


class MdJobOut(JobOut):
    pass


class MdJobListOut(BaseModel):
    items: list[MdJobOut]
    total: int


class JobListOut(BaseModel):
    items: list[JobOut]
    total: int


class HealthOut(BaseModel):
    status: str
    database: str
    redis: str
    queue_depth: int | None = None
    running_jobs: int | None = None
    gpu_workers: int | None = None


class CdrSpanOut(BaseModel):
    name: str
    start: int
    end: int
    kabat_range: str
    sequence: str


class SequenceSegmentOut(BaseModel):
    type: str
    text: str
    name: str | None = None


class ResidueOut(BaseModel):
    index: int
    aa: str
    kabat: str


class ChainSequenceOut(BaseModel):
    chain_id: str
    length: int
    sequence: str
    is_antibody: bool
    domain: str | None
    scheme: str | None
    cdr_spans: list[CdrSpanOut]
    segments: list[SequenceSegmentOut]
    residues: list[ResidueOut] = Field(default_factory=list)


class JobSequencesOut(BaseModel):
    job_id: str
    chains: list[ChainSequenceOut]


class InterfaceResidueOut(BaseModel):
    chain_id: str
    seq_num: int
    resname: str


class InterfaceInteractionOut(BaseModel):
    type: str
    chain_a: str
    resnum_a: int
    resname_a: str
    atom_a: str
    chain_b: str
    resnum_b: int
    resname_b: str
    atom_b: str
    distance_angstrom: float
    coord_a: list[float]
    coord_b: list[float]
    detail: str = ""


class InterfaceInteractionSummaryOut(BaseModel):
    n_hbonds: int = 0
    n_salt_bridges: int = 0
    n_hydrophobic: int = 0
    n_polar_contacts: int = 0
    n_contacts: int = 0
    n_total: int = 0
    n_interface_residues_a: int = 0
    n_interface_residues_b: int = 0


class InterfacePairOut(BaseModel):
    chain_a: str
    chain_b: str
    label_a: str | None = None
    label_b: str | None = None
    contact_pairs: int
    avg_interface_plddt: float | None = None
    avg_interface_pae: float | None = None
    pdockq: float
    pdockq2: float
    residues_a: list[InterfaceResidueOut]
    residues_b: list[InterfaceResidueOut]
    interactions: list[InterfaceInteractionOut] = Field(default_factory=list)
    interaction_summary: InterfaceInteractionSummaryOut | None = None


class InterfaceChainOut(BaseModel):
    chain_id: str
    length: int
    label: str
    role: str
    color: str
    is_antibody: bool = False


class InterfaceReferenceToolOut(BaseModel):
    name: str
    role: str
    url: str


class JobInterfaceOut(BaseModel):
    job_id: str
    error: str | None = None
    contact_cutoff_angstrom: float = 8.0
    method: str | None = None
    reference_tools: list[InterfaceReferenceToolOut] = Field(default_factory=list)
    chains: list[InterfaceChainOut] = Field(default_factory=list)
    interfaces: list[InterfacePairOut] = Field(default_factory=list)
    primary_interface: InterfacePairOut | None = None


class TargetInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    chain_id: str = Field(default="A", max_length=16)
    sequence: str = Field(min_length=5)


class HeavyChainInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    sequence: str = Field(min_length=5)


class VhhPanelCreate(BaseModel):
    batch_name: str | None = Field(default=None, max_length=128)
    target: TargetInput
    heavy_chain_id: str = Field(default="H", max_length=16)
    heavy_chains: list[HeavyChainInput] = Field(min_length=1)
    engine: Literal["boltz2", "esmfold2"] = "boltz2"
    use_msa_server: bool = True
    esmfold_params: EsmFold2Params | None = None


class BatchJobOut(JobOut):
    pass


class BatchOut(BaseModel):
    id: str
    name: str
    batch_type: str
    target_name: str
    target_chain_id: str
    heavy_chain_id: str
    heavy_chain_count: int
    use_msa_server: bool
    created_at: datetime
    status: str
    done_count: int
    running_count: int
    queued_count: int
    failed_count: int
    cancelled_count: int

    model_config = {"from_attributes": True}


class BatchDetailOut(BatchOut):
    target_sequence: str


class BatchJobsListOut(BaseModel):
    items: list[BatchJobOut]
    total: int
    limit: int
    offset: int


class BatchListOut(BaseModel):
    items: list[BatchOut]
    total: int


class VhhPanelCreateOut(BaseModel):
    batch: BatchOut
    job_ids: list[str]
    skipped_duplicates: int = 0


class HeavyCsvParseRow(BaseModel):
    id: str
    sequence: str


class HeavyCsvParseOut(BaseModel):
    text: str
    encoding: str
    format: Literal["csv", "fasta"] = "csv"
    rows: list[HeavyCsvParseRow]
    row_count: int


class HeavyCsvParseB64(BaseModel):
    filename: str = Field(default="upload.csv", max_length=256)
    content_b64: str = Field(min_length=1)
