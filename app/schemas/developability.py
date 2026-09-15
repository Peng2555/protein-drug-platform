"""Developability schemas."""

from typing import Literal

from pydantic import BaseModel, Field

from .common.jobs import JobOut


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
