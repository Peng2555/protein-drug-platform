"""Shared job creation and queueing."""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import DEFAULT_FOLD_ENGINE, normalize_fold_engine
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_fold_job


def sequence_hash(seqs: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(seqs, sort_keys=True).encode()).hexdigest()


def fasta_from_seqs(seqs: dict[str, str]) -> str:
    lines = []
    for cid, seq in seqs.items():
        lines.append(f">{cid}")
        lines.append(seq)
    return "\n".join(lines) + "\n"


def _check_user_queue_cap(db: Session, user_id: str, engine: str) -> None:
    """Optional abuse guard; 0 = unlimited queued jobs."""
    cap = settings.max_jobs_per_user_queued
    if cap <= 0:
        return
    pending = db.scalar(
        select(func.count())
        .select_from(Job)
        .where(
            Job.user_id == user_id,
            Job.engine == engine,
            Job.status.in_([JobStatus.queued.value, JobStatus.running.value]),
        )
    )
    if pending and pending >= cap:
        raise HTTPException(429, f"Max {cap} pending jobs per user (queued + running)")


def _esmfold_job_params(custom: dict | None = None) -> dict:
    params = {
        "model": settings.esmfold_model,
        "num_loops": 10,
        "num_sampling_steps": 68,
        "num_diffusion_samples": 5,
        "seed": 0,
    }
    if custom:
        params.update({k: v for k, v in custom.items() if v is not None})
    return params


def _boltz_job_params(custom: dict | None = None, *, use_msa_server: bool = True) -> dict:
    params = {
        "recycling_steps": 3,
        "sampling_steps": 200,
        "diffusion_samples": 1,
        "max_parallel_samples": 5,
        "step_scale": None,
        "seed": None,
        "output_format": "mmcif",
        "model": "boltz2",
        "method": None,
        "use_potentials": False,
        "use_msa_server": use_msa_server,
        "msa_pairing_strategy": "greedy",
        "max_msa_seqs": 8192,
        "subsample_msa": False,
        "num_subsampled_msa": 1024,
        "write_full_pae": False,
        "write_full_pde": False,
        "write_embeddings": False,
    }
    if custom:
        params.update({k: v for k, v in custom.items() if k in params})
    # 表单顶层 use_msa_server 与 boltz_params 保持一致
    params["use_msa_server"] = bool(params.get("use_msa_server", use_msa_server))
    return params


def dispatch_job(db: Session, job: Job) -> None:
    """Send an already-committed job to the GPU queue."""
    async_result = dispatch_to_gpu(run_fold_job, job.id)
    job.celery_task_id = async_result.id


def create_and_queue_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    chains_json: dict[str, int],
    total_length: int,
    seq_hash: str,
    use_msa_server: bool = True,
    batch_id: str | None = None,
    heavy_chain_id: str | None = None,
    skip_running_limit: bool = False,
    reference_pdb_path: str | None = None,
    engine: str = DEFAULT_FOLD_ENGINE,
    boltz_params: dict | None = None,
    esmfold_params: dict | None = None,
    defer_dispatch: bool = False,
) -> Job:
    fold_engine = normalize_fold_engine(engine)
    if not skip_running_limit:
        _check_user_queue_cap(db, user_id, fold_engine)

    if fold_engine == "esmfold2":
        params = _esmfold_job_params(esmfold_params)
    else:
        params = _boltz_job_params(boltz_params, use_msa_server=use_msa_server)
        use_msa_server = bool(params.get("use_msa_server", use_msa_server))

    job = Job(
        user_id=user_id,
        batch_id=batch_id,
        heavy_chain_id=heavy_chain_id,
        name=name,
        engine=fold_engine,
        status=JobStatus.queued.value,
        fasta_text=fasta_text,
        sequence_hash=seq_hash,
        chains_json=chains_json,
        total_length=total_length,
        use_msa_server=use_msa_server if fold_engine == "boltz2" else False,
        params_json=params,
    )
    if reference_pdb_path:
        job.params_json = {
            **(job.params_json or {}),
            "reference_pdb": reference_pdb_path,
            "compute_dockq": True,
        }
    db.add(job)
    db.flush()
    if not defer_dispatch:
        dispatch_job(db, job)
    return job


def requeue_queued_jobs(db: Session, *, batch_id: str | None = None) -> int:
    """Re-dispatch jobs stuck in queued (e.g. after a failed early dispatch)."""
    q = select(Job).where(Job.status == JobStatus.queued.value)
    if batch_id:
        q = q.where(Job.batch_id == batch_id)
    jobs = db.scalars(q).all()
    for job in jobs:
        dispatch_job(db, job)
    return len(jobs)
