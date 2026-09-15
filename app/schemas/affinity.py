"""Affinity redesign schemas."""

from pydantic import BaseModel, Field

from .common.jobs import JobOut
from .maturation import MaturationLogSection


class AffinityRedesignJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fasta: str = Field(min_length=20, description="H/L/A 等多链 FASTA")
    skip_round1: bool = False
    consensus_k: int = Field(default=3, ge=1, le=6, description="PLM 共识：至少 k 个模型 dll>0")


class AffinityRedesignJobOut(JobOut):
    pass


class AffinityRedesignJobListOut(BaseModel):
    items: list[AffinityRedesignJobOut]
    total: int


class AffinityRedesignRankedOut(BaseModel):
    ranked: list[dict] = Field(default_factory=list)
    wetlab: list[dict] = Field(default_factory=list)
    summary: dict | None = None
    mutation_table: list[dict] = Field(default_factory=list)


class AffinityRedesignProgressOut(BaseModel):
    stage: str | None = None
    status: str
    summary_lines: list[str] = Field(default_factory=list)
    progress: dict = Field(default_factory=dict)
    sections: list[MaturationLogSection] = Field(default_factory=list)
    workflow_status: dict | None = None
    plm_hits: list[dict] = Field(default_factory=list)
    structure_hits: list[dict] = Field(default_factory=list)
    mutation_table: list[dict] = Field(default_factory=list)
