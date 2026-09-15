"""Protein design schemas."""

from pydantic import BaseModel, Field

from .common.jobs import JobOut


class DesignJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    fold_job_id: str | None = None
    designed_chains: str = Field(default="", max_length=64, description="要设计的链，空格分隔，如 H A；空=全部")
    num_seq_per_target: int = Field(default=8, ge=1, le=64)
    sampling_temp: float = Field(default=0.1, ge=0.05, le=1.0)
    seed: int = Field(default=0, ge=0, le=999999)
    backbone_noise: float = Field(default=0.0, ge=0.0, le=1.0)
    omit_aas: str = Field(default="X", max_length=32)


class DesignJobOut(JobOut):
    pass


class DesignJobListOut(BaseModel):
    items: list[DesignJobOut]
    total: int
