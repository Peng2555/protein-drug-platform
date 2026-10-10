"""额外二硫键 / Tm 筛选 schemas。"""

from datetime import datetime

from pydantic import BaseModel, Field

from .common.jobs import JobOut


class TmDisulfideJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    source_job_id: str = Field(min_length=8, description="已完成的 Boltz2 作业 ID")


class TmDisulfideJobOut(JobOut):
    pass


class TmDisulfideJobListOut(BaseModel):
    items: list[TmDisulfideJobOut]
    total: int


class TmDisulfideProgressOut(BaseModel):
    stage: str
    status: str
    summary: dict | None = None


class TmDisulfideRankedOut(BaseModel):
    candidates: list[dict] = Field(default_factory=list)
    summary: dict | None = None


class TmDisulfideSourceFoldJobOut(BaseModel):
    id: str
    name: str | None = None
    status: str
    n_models: int
    total_length: int | None = None
    created_at: datetime


class TmDisulfideSourceFoldJobListOut(BaseModel):
    items: list[TmDisulfideSourceFoldJobOut]
    total: int
