"""Docking schemas."""

from typing import Literal

from pydantic import BaseModel, Field

from .common.jobs import JobOut


class RasDockingJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    project: Literal["rmc6236", "rmc6291"] = "rmc6236"
    stage: Literal[
        "fetch", "prepare", "redock", "screen", "contacts", "literature",
        "download", "dock",
    ] = "literature"
    system: str = Field(default="rmc6291", max_length=64)


class RasDockingJobOut(JobOut):
    pass


class RasDockingJobListOut(BaseModel):
    items: list[RasDockingJobOut]
    total: int


class DockingJobCreate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    engine: Literal["vina", "gnina"] = "vina"
    dock_mode: Literal["auto_blind", "reference", "manual"] = "auto_blind"
    num_cavities: int = Field(default=5, ge=1, le=19)
    ligand_smiles: str = Field(default="", max_length=4000)
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    size_x: float = Field(default=22.0, gt=0, le=100)
    size_y: float = Field(default=22.0, gt=0, le=100)
    size_z: float = Field(default=22.0, gt=0, le=100)
    exhaustiveness: int = Field(default=8, ge=1, le=64)
    num_modes: int = Field(default=20, ge=1, le=50)
    energy_range: float = Field(default=5.0, ge=0, le=20)
    n_starts: int = Field(default=3, ge=1, le=10)
    n_conformers: int = Field(default=128, ge=8, le=256)
    box_padding: float = Field(default=5.0, gt=0, le=20)


class DockingJobOut(JobOut):
    pass


class DockingJobListOut(BaseModel):
    items: list[DockingJobOut]
    total: int
