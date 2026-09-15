"""CIC profile schemas."""

from pydantic import BaseModel, Field

from .common.jobs import JobOut


class CicProfileJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fasta: str = Field(min_length=20, description="抗体 FASTA，链 ID 为 H 或 H+L")
    ph: float = Field(default=7.0, ge=4.0, le=10.0)


class CicProfileJobOut(JobOut):
    pass


class CicProfileJobListOut(BaseModel):
    items: list[CicProfileJobOut]
    total: int


class CicProfileProgressOut(BaseModel):
    stage: str
    status: str
    summary: dict | None = None


class CicProfileRankedOut(BaseModel):
    patches: list[dict] = Field(default_factory=list)
    residues: list[dict] = Field(default_factory=list)
    summary: dict | None = None
