"""Synthesis selection schemas."""

from pydantic import BaseModel, Field

from .common.jobs import JobOut


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
