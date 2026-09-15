"""Affinity maturation schemas."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .common.jobs import JobOut


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
