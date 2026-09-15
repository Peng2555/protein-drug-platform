"""TNP profile schemas."""

from pydantic import BaseModel, Field

from .batch import BatchOut
from .common.jobs import JobOut


class TnpProfileJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fasta: str = Field(min_length=20, description="VHH FASTA，链 ID 为 H")


class TnpProfileBatchCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fasta: str = Field(min_length=20, description="多条 VHH FASTA，每条记录一条重链")


class TnpProfileJobOut(JobOut):
    pass


class TnpProfileJobListOut(BaseModel):
    items: list[TnpProfileJobOut]
    total: int


class TnpProfileProgressOut(BaseModel):
    stage: str
    status: str
    summary: dict | None = None


class TnpProfileRankedOut(BaseModel):
    patches: list[dict] = Field(default_factory=list)
    residues: list[dict] = Field(default_factory=list)
    metrics: list[dict] = Field(default_factory=list)
    summary: dict | None = None


class TnpProfileBatchCreateOut(BaseModel):
    batch: BatchOut
    job_ids: list[str]
