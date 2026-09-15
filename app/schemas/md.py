"""Molecular dynamics schemas."""

from pydantic import BaseModel, Field

from .common.jobs import JobOut


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
