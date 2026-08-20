"""Pydantic schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator


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


class RasDockingJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    project: Literal["rmc6236", "rmc6291"] = "rmc6236"
    stage: Literal[
        "fetch", "prepare", "redock", "screen", "contacts", "literature",
        "download", "dock",
    ] = "literature"
    system: str = Field(default="rmc6291", max_length=64)


class RasDockingJobOut(JobOut):
    pass


class RasDockingJobListOut(BaseModel):
    items: list[RasDockingJobOut]
    total: int


class DockingJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    engine: Literal["vina", "gnina"] = "vina"
    dock_mode: Literal["auto_blind", "reference", "manual"] = "auto_blind"
    num_cavities: int = Field(default=5, ge=1, le=19)
    ligand_smiles: str = Field(default="", max_length=4000)
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    size_x: float = Field(default=22.0, gt=0, le=100)
    size_y: float = Field(default=22.0, gt=0, le=100)
    size_z: float = Field(default=22.0, gt=0, le=100)
    exhaustiveness: int = Field(default=8, ge=1, le=64)
    num_modes: int = Field(default=20, ge=1, le=50)
    energy_range: float = Field(default=5.0, ge=0, le=20)
    n_starts: int = Field(default=3, ge=1, le=10)
    n_conformers: int = Field(default=128, ge=8, le=256)
    box_padding: float = Field(default=5.0, gt=0, le=20)


class DockingJobOut(JobOut):
    pass


class DockingJobListOut(BaseModel):
    items: list[DockingJobOut]
    total: int


class DevelopabilityJobCreate(BaseModel):
    fasta: str = Field(min_length=10)
    name: str | None = Field(default=None, max_length=128)
    goal: Literal["hydro", "tm", "both"] = "both"
    freeze_cysteine: bool = True
    freeze_cdr3: bool = True
    freeze_all_cdrs: bool = False
    dll_threshold: float = Field(default=0.0, ge=-5.0, le=5.0)
    max_mutants_per_site: int = Field(default=19, ge=1, le=19)
    run_maxwell: bool = True
    fold_job_id: str | None = None


class DevelopabilityJobOut(JobOut):
    fasta_text: str | None = None


class DevelopabilityJobListOut(BaseModel):
    items: list[DevelopabilityJobOut]
    total: int


class DesignJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fold_job_id: str | None = None
    designed_chains: str = Field(default="", max_length=64, description="要设计的链，空格分隔，如 H A；空=全部")
    num_seq_per_target: int = Field(default=8, ge=1, le=64)
    sampling_temp: float = Field(default=0.1, ge=0.05, le=1.0)
    seed: int = Field(default=0, ge=0, le=999999)
    backbone_noise: float = Field(default=0.0, ge=0.0, le=1.0)
    omit_aas: str = Field(default="X", max_length=32)


class DesignJobOut(JobOut):
    pass


class DesignJobListOut(BaseModel):
    items: list[DesignJobOut]
    total: int


class IgGMParams(BaseModel):
    num_samples: int = Field(default=100, ge=1, le=500)
    steps: int = Field(default=10, ge=1, le=50)
    max_antigen_size: int = Field(default=384, ge=50, le=2000)
    temperature: float = Field(default=1.0, ge=0.1, le=2.0)
    chunk_size: int = Field(default=64, ge=8, le=256)
    relax: bool = False
    gpu_count: int = Field(default=2, ge=1, le=8)
    gpu_ids: list[int] | None = None
    epitope: list[int] | None = None


class MaturationJobCreate(BaseModel):
    fasta: str | None = Field(default=None, min_length=10)
    name: str | None = Field(default=None, max_length=128)
    structure_source: Literal["upload", "boltz2", "esmfold2", "fold_job"] = "upload"
    fold_job_id: str | None = None
    binder_chain_id: str = Field(default="H", max_length=16)
    antigen_chain_id: str = Field(default="A", max_length=16)
    cdr_mask: list[str] = Field(default_factory=lambda: ["CDR-H3"])
    iggm: IgGMParams | None = None
    fold_params: dict | None = None
    use_msa_server: bool = True

    @model_validator(mode="after")
    def fasta_required_for_prediction(self) -> "MaturationJobCreate":
        if self.structure_source in ("boltz2", "esmfold2") and not (self.fasta and self.fasta.strip()):
            raise ValueError("使用 Boltz2/ESMFold2 预测结构时必须提供 FASTA 序列")
        return self


class MaturationJobOut(JobOut):
    pass


class MaturationJobListOut(BaseModel):
    items: list[MaturationJobOut]
    total: int


class MaturationVariantOut(BaseModel):
    method: str | None = None
    antibody_seq_h: str | None = None
    frequency: int | None = None
    diff: str | None = None
    mutations: str | None = None
    extra: dict = Field(default_factory=dict)


class MaturationVariantsOut(BaseModel):
    items: list[MaturationVariantOut]
    total: int
    columns: list[str] = Field(default_factory=list)


class MaturationLogSection(BaseModel):
    id: str
    title: str
    content: str
    truncated: bool = False


class MaturationLogsOut(BaseModel):
    stage: str | None = None
    status: str
    summary_lines: list[str] = Field(default_factory=list)
    progress: dict = Field(default_factory=dict)
    sections: list[MaturationLogSection] = Field(default_factory=list)


class SynthesisSelectParams(BaseModel):
    min_seq_count: float = Field(default=10.0, ge=0)
    top_n: int = Field(default=30, ge=1, le=500)
    mutation_min: int = Field(default=1, ge=0, le=10)
    mutation_max: int = Field(default=3, ge=1, le=10)
    seq_col: str | None = None
    cdr3_col: str | None = None
    count_col: str | None = None


class SynthesisSelectOut(BaseModel):
    job_id: str | None = None
    parent_cdr3: str | None = None
    parent_v_gene: str | None = None
    cdr3_region: str | None = None
    shm_filtered: int
    matched_count: int
    matched_cdr3_kinds: int
    unmatched_iggm_count: int
    order_count: int
    a_count: int
    b_count: int
    matched_csv: str
    unmatched_csv: str
    order_csv: str
    order_txt: str
    out_dir: str


class SynthesisCandidateOut(BaseModel):
    synthesis_id: str | None = None
    priority: str | None = None
    recommend: str | None = None
    iggm_variant_id: str | None = None
    iggm_cdr3: str | None = None
    seq_count: float | None = None
    shm_row: int | None = None
    cdr3_mutation_sites: str | None = None
    extra_mutation_sites: str | None = None
    all_mutation_sites_for_synthesis: str | None = None
    n_total_mutations: int | None = None
    synthesis_sequence: str | None = None
    nucleotide_sequence: str | None = None
    v_gene: str | None = None
    j_gene: str | None = None
    PI: str | None = None
    note: str | None = None
    has_extra_shm: str | None = None
    cdr3_mutation_sites_in_shm_row: str | None = None
    extra_mutation_sites_in_shm_row: str | None = None
    aa_sequence: str | None = None
    iggm_frequency: float | None = None
    iggm_cdr3_mutations: str | None = None
    extra: dict = Field(default_factory=dict)


class SynthesisCandidatesOut(BaseModel):
    items: list[SynthesisCandidateOut]
    total: int
    columns: list[str] = Field(default_factory=list)
    summary: dict | None = None


class SynthesisJobOut(JobOut):
    pass


class SynthesisJobListOut(BaseModel):
    items: list[SynthesisJobOut]
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
