"""Shared job response schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


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
