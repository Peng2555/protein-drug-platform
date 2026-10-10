"""Batch structure prediction schemas."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from .common.jobs import JobOut
from .fold import Boltz2Params, EsmFold2Params


class TargetInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    chain_id: str = Field(default="A", max_length=16)
    sequence: str = Field(min_length=5)


class HeavyChainInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    sequence: str = Field(min_length=5)


class VhhPanelCreate(BaseModel):
    batch_name: str | None = Field(default=None, max_length=128)
    target: TargetInput
    heavy_chain_id: str = Field(default="H", max_length=16)
    heavy_chains: list[HeavyChainInput] = Field(min_length=1)
    engine: Literal["boltz2", "esmfold2"] = "boltz2"
    use_msa_server: bool = True
    boltz_params: Boltz2Params | None = None
    esmfold_params: EsmFold2Params | None = None


class AntibodyInput(BaseModel):
    id: str = Field(min_length=1, max_length=64)
    heavy: str = Field(min_length=5)
    light: str | None = None


class AntibodyOnlyCreate(BaseModel):
    batch_name: str | None = Field(default=None, max_length=128)
    heavy_chain_id: str = Field(default="H", max_length=16)
    light_chain_id: str = Field(default="L", max_length=16)
    antibodies: list[AntibodyInput] = Field(min_length=1)
    engine: Literal["boltz2", "esmfold2"] = "boltz2"
    use_msa_server: bool = True
    boltz_params: Boltz2Params | None = None
    esmfold_params: EsmFold2Params | None = None


class BatchJobOut(JobOut):
    pass


class BatchOut(BaseModel):
    id: str
    name: str
    batch_type: str
    target_name: str
    target_chain_id: str
    heavy_chain_id: str
    heavy_chain_count: int
    use_msa_server: bool
    created_at: datetime
    status: str
    done_count: int
    running_count: int
    queued_count: int
    failed_count: int
    cancelled_count: int

    model_config = {"from_attributes": True}


class BatchDetailOut(BatchOut):
    target_sequence: str


class BatchJobsListOut(BaseModel):
    items: list[BatchJobOut]
    total: int
    limit: int
    offset: int


class BatchListOut(BaseModel):
    items: list[BatchOut]
    total: int


class VhhPanelCreateOut(BaseModel):
    batch: BatchOut
    job_ids: list[str]
    skipped_duplicates: int = 0


class HeavyCsvParseRow(BaseModel):
    id: str
    sequence: str


class HeavyCsvParseOut(BaseModel):
    text: str
    encoding: str
    format: Literal["csv", "fasta"] = "csv"
    rows: list[HeavyCsvParseRow]
    row_count: int


class HeavyCsvParseB64(BaseModel):
    filename: str = Field(default="upload.csv", max_length=256)
    content_b64: str = Field(min_length=1)


class AntibodyParseRow(BaseModel):
    id: str
    heavy: str
    light: str | None = None


class AntibodyParseOut(BaseModel):
    text: str
    encoding: str
    format: Literal["csv", "fasta"] = "csv"
    rows: list[AntibodyParseRow]
    row_count: int
