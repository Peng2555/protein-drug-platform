"""Masking peptide schemas."""

from pydantic import BaseModel, Field

from .common.jobs import JobOut


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
