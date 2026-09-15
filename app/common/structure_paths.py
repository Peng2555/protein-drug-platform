"""Neutral structure-path resolution shared by downstream services."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from app.config import settings
from app.models import Job


def resolve_structure_path(parent: Job) -> Path:
    if parent.structure_path:
        path = Path(parent.structure_path)
        if path.is_file():
            return path
    if parent.work_dir:
        for name in ("pred.cif", "pred.pdb"):
            candidate = Path(parent.work_dir) / name
            if candidate.is_file():
                return candidate
    for name in ("pred.cif", "pred.pdb"):
        legacy = settings.boltz2_out_root / parent.id / name
        if legacy.is_file():
            return legacy
    raise HTTPException(400, "Parent job has no structure file")
