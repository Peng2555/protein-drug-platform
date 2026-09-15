"""Rosetta evaluation schemas."""

from pydantic import BaseModel, Field

from .common.jobs import JobOut


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
