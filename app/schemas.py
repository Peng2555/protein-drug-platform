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


class Boltz2Params(BaseModel):
    """Boltz2 predict CLI 参数（与本机 boltz predict 对齐）。"""

    recycling_steps: int = Field(default=3, ge=1, le=20)
    sampling_steps: int = Field(default=200, ge=20, le=1000)
    diffusion_samples: int = Field(default=1, ge=1, le=25)
    max_parallel_samples: int | None = Field(default=5, ge=1, le=25)
    step_scale: float | None = Field(default=None, ge=0.5, le=5.0)
    seed: int | None = Field(default=None, ge=0, le=2_147_483_647)
    output_format: Literal["mmcif", "pdb"] = "mmcif"
    model: Literal["boltz2", "boltz1"] = "boltz2"
    method: str | None = Field(default=None, max_length=64)
    use_potentials: bool = False
    use_msa_server: bool = True
    msa_pairing_strategy: Literal["greedy", "complete"] = "greedy"
    max_msa_seqs: int = Field(default=8192, ge=64, le=16384)
    subsample_msa: bool = False
    num_subsampled_msa: int = Field(default=1024, ge=16, le=8192)
    write_full_pae: bool = False
    write_full_pde: bool = False
    write_embeddings: bool = False


class BoltzModification(BaseModel):
    position: int = Field(ge=1, le=10000)
    ccd: str = Field(min_length=1, max_length=16)


class BoltzComponent(BaseModel):
    """一条唯一实体；copies>1 时展开为多个链 ID（与 Tamarind / Boltz YAML 一致）。"""

    entity: Literal["protein", "dna", "rna", "ligand"] = "protein"
    ids: list[str] = Field(min_length=1)
    sequence: str | None = None
    smiles: str | None = None
    ccd: str | None = None
    cyclic: bool = False
    modifications: list[BoltzModification] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_entity_fields(self):
        ids = [i.strip() for i in self.ids if i and i.strip()]
        if not ids:
            raise ValueError("每条链至少需要一个 ID")
        if len(ids) != len(set(ids)):
            raise ValueError(f"链 ID 重复: {ids}")
        for cid in ids:
            if len(cid) > 4:
                raise ValueError(f"链 ID「{cid}」超过 4 个字符")
        object.__setattr__(self, "ids", ids)

        if self.entity == "ligand":
            has_smi = bool(self.smiles and self.smiles.strip())
            has_ccd = bool(self.ccd and self.ccd.strip())
            if has_smi == has_ccd:
                raise ValueError("配体需且仅需提供 SMILES 或 CCD 之一")
        else:
            seq = (self.sequence or "").replace(" ", "").replace("\n", "").upper()
            if len(seq) < 2:
                raise ValueError(f"{self.entity} 序列过短")
            object.__setattr__(self, "sequence", seq)
        return self


class BoltzPocketConstraint(BaseModel):
    type: Literal["pocket"] = "pocket"
    binder: str = Field(min_length=1, max_length=4)
    contacts: list[tuple[str, int]] = Field(min_length=1)
    max_distance: float = Field(default=6.0, ge=4.0, le=20.0)
    force: bool = False


class BoltzContactConstraint(BaseModel):
    type: Literal["contact"] = "contact"
    token1: tuple[str, int]
    token2: tuple[str, int]
    max_distance: float = Field(default=6.0, ge=4.0, le=20.0)
    force: bool = False


class BoltzAffinity(BaseModel):
    """仅支持小分子配体相对蛋白靶点的亲和力头（非蛋白–蛋白）。"""

    binder: str = Field(min_length=1, max_length=4)


class JobCreate(BaseModel):
    fasta: str | None = None
    chains: list[ChainInput] | None = None
    name: str | None = Field(default=None, max_length=128)
    engine: Literal["boltz2", "esmfold2"] = "boltz2"
    use_msa_server: bool = True
    boltz_params: Boltz2Params | None = None
    esmfold_params: EsmFold2Params | None = None
    # Boltz 结构化输入（优先于纯 FASTA）
    components: list[BoltzComponent] | None = None
    constraints: list[BoltzPocketConstraint | BoltzContactConstraint] | None = None
    affinity: BoltzAffinity | None = None

    @model_validator(mode="after")
    def _check_input(self):
        has_comp = bool(self.components)
        has_fasta = bool(self.fasta and self.fasta.strip()) or bool(self.chains)
        if self.engine == "boltz2":
            if not has_comp and not has_fasta:
                raise ValueError("请提供 components 或 fasta")
            if self.affinity and has_comp:
                binder = self.affinity.binder
                ligand_ids = {
                    cid
                    for c in self.components or []
                    if c.entity == "ligand"
                    for cid in c.ids
                }
                if binder not in ligand_ids:
                    raise ValueError(
                        f"亲和力 binder「{binder}」必须是小分子配体链 ID；"
                        "Boltz-2 亲和力模块仅支持小分子–蛋白，不支持蛋白–蛋白。"
                    )
                for c in self.components or []:
                    if binder in c.ids and len(c.ids) > 1:
                        raise ValueError("亲和力配体不能有多个 copies")
        else:
            if not has_fasta and not has_comp:
                raise ValueError("请提供序列输入")
        return self


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


class RosettaEvalJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    wt_fold_job_id: str | None = None
    mutant_fold_job_ids: list[str] = Field(default_factory=list)
    nstruct: int = Field(default=3, ge=1, le=10)
    n_jobs: int = Field(default=16, ge=1, le=64, description="并行 CPU 进程数")
    antibody_chains: str = Field(default="", max_length=32, description="空格分隔，空则自动识别")
    antigen_chains: str = Field(default="", max_length=32)


class RosettaEvalJobOut(JobOut):
    pass


class RosettaEvalJobListOut(BaseModel):
    items: list[RosettaEvalJobOut]
    total: int


class AffinityRedesignJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fasta: str = Field(min_length=20, description="H/L/A 等多链 FASTA")
    skip_round1: bool = False


class AffinityRedesignJobOut(JobOut):
    pass


class AffinityRedesignJobListOut(BaseModel):
    items: list[AffinityRedesignJobOut]
    total: int


class AffinityRedesignRankedOut(BaseModel):
    ranked: list[dict] = Field(default_factory=list)
    wetlab: list[dict] = Field(default_factory=list)
    summary: dict | None = None


class MaskingPeptideJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fold_job_id: str | None = None
    hotspot_res: list[str] = Field(default_factory=lambda: ["H35", "H47", "H50", "H104", "H110"])
    target_chain: str = Field(default="H", max_length=8)
    peptide_length: str = Field(default="12-18", max_length=16)
    total_designs: int = Field(default=200, ge=10, le=20000)
    mpnn_rounds: int = Field(default=4, ge=1, le=8)
    skip_backbone: bool = False
    relax_jobs: int = Field(default=8, ge=1, le=32)


class MaskingPeptideJobOut(JobOut):
    pass


class MaskingPeptideJobListOut(BaseModel):
    items: list[MaskingPeptideJobOut]
    total: int


class MaskingPeptideSequencesOut(BaseModel):
    sequences: list[dict] = Field(default_factory=list)
    summary: dict | None = None


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


class AffinityRedesignProgressOut(BaseModel):
    stage: str | None = None
    status: str
    summary_lines: list[str] = Field(default_factory=list)
    progress: dict = Field(default_factory=dict)
    sections: list[MaturationLogSection] = Field(default_factory=list)
    workflow_status: dict | None = None
    plm_hits: list[dict] = Field(default_factory=list)
    structure_hits: list[dict] = Field(default_factory=list)


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
    boltz_params: Boltz2Params | None = None
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
