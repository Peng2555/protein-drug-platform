"""Hydrophobicity redesign schemas."""

from pydantic import BaseModel, Field

from .batch import BatchOut
from .common.jobs import JobOut


class HydroRedesignJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fasta: str = Field(min_length=20, description="抗体 FASTA，链 ID 为 H 或 H+L")
    allow_cdr: bool = False
    allow_charged: bool = False


class HydroRedesignBatchCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fasta: str = Field(min_length=20, description="多条 VHH FASTA，每条记录一条重链")
    allow_cdr: bool = False
    allow_charged: bool = False


class HydroRedesignJobOut(JobOut):
    pass


class HydroRedesignJobListOut(BaseModel):
    items: list[HydroRedesignJobOut]
    total: int


class HydroRedesignProgressOut(BaseModel):
    stage: str
    status: str
    summary: dict | None = None


class HydroRedesignRankedOut(BaseModel):
    mutations: list[dict] = Field(default_factory=list)
    wetlab: list[dict] = Field(default_factory=list)
    patches: list[dict] = Field(default_factory=list)
    residues: list[dict] = Field(default_factory=list)
    summary: dict | None = None


class HydroRedesignBatchCreateOut(BaseModel):
    batch: BatchOut
    job_ids: list[str]
