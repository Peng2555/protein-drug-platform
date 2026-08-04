"""MD job creation and queueing."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.job_paths import job_output_dir
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_md_job


def md_sequence_hash(source: str) -> str:
    return hashlib.sha256(source.encode()).hexdigest()


def resolve_structure_path(parent: Job) -> Path:
    if parent.structure_path:
        path = Path(parent.structure_path)
        if path.is_file():
            return path
    if parent.work_dir:
        candidate = Path(parent.work_dir) / "pred.cif"
        if candidate.is_file():
            return candidate
    legacy = settings.boltz2_out_root / parent.id / "pred.cif"
    if legacy.is_file():
        return legacy
    raise HTTPException(400, "Parent job has no structure file")


def create_and_queue_md_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    input_structure: Path,
    parent_job_id: str | None = None,
    fasta_text: str = ">md\n.",
    chains_json: dict | None = None,
    production_ns: float | None = None,
    replicas: int | None = None,
    antigen_chain: str = "A",
    binder_chain: str = "H",
) -> Job:
    from app.job_service import _check_user_queue_cap

    _check_user_queue_cap(db, user_id, "gromacs_md")

    prod_ns = production_ns if production_ns is not None else settings.md_production_ns
    n_rep = replicas if replicas is not None else settings.md_replicas
    chains = chains_json or {"structure": 1}

    job = Job(
        user_id=user_id,
        parent_job_id=parent_job_id,
        name=name,
        engine="gromacs_md",
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=fasta_text,
        sequence_hash=md_sequence_hash(str(input_structure)),
        chains_json=chains,
        total_length=sum(chains.values()) if chains else 0,
        use_msa_server=False,
        params_json={
            "production_ns": prod_ns,
            "replicas": n_rep,
            "antigen_chain": antigen_chain,
            "binder_chain": binder_chain,
            "input_structure": str(input_structure),
        },
    )
    db.add(job)
    db.flush()

    work_dir = job_output_dir(settings.md_out_root, job.name, job.id, chains)
    struct_dir = work_dir / "00_structure"
    struct_dir.mkdir(parents=True, exist_ok=True)
    dest = struct_dir / input_structure.name
    if input_structure.resolve() != dest.resolve():
        shutil.copy2(input_structure, dest)

    job.work_dir = str(work_dir)
    job.params_json = {**(job.params_json or {}), "input_structure": str(dest)}

    async_result = dispatch_to_gpu(run_md_job, job.id)
    job.celery_task_id = async_result.id
    return job


async def save_uploaded_structure(upload: UploadFile, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "input.cif").suffix.lower()
    if suffix not in {".cif", ".mmcif", ".pdb"}:
        raise HTTPException(400, "Upload .cif or .pdb structure file")
    dest = dest_dir / f"upload{suffix}"
    content = await upload.read()
    if len(content) < 100:
        raise HTTPException(400, "Structure file too small or empty")
    dest.write_bytes(content)
    return dest
