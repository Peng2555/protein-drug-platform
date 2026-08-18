"""ESM-2 developability redesign job service."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import DEVELOPABILITY_ENGINE
from app.job_paths import job_output_dir
from app.job_service import fasta_from_seqs, sequence_hash
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_developability_job

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from boltz_runner import parse_fasta_text


def create_and_queue_developability_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    fasta_text: str,
    params: dict,
) -> Job:
    try:
        seqs = parse_fasta_text(fasta_text)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not seqs:
        raise HTTPException(400, "FASTA 为空")
    chains_json = {cid: len(seq) for cid, seq in seqs.items()}
    total_length = sum(chains_json.values())
    if total_length > settings.max_total_sequence_length:
        raise HTTPException(400, f"序列总长 {total_length} 超过上限")

    stored = fasta_from_seqs(seqs)
    job = Job(
        user_id=user_id,
        name=name,
        engine=DEVELOPABILITY_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=stored,
        sequence_hash=sequence_hash(seqs),
        chains_json=chains_json,
        total_length=total_length,
        use_msa_server=False,
        params_json={
            **params,
            "model_path": str(settings.esm2_3b_path),
            "parent_id": name,
        },
    )
    db.add(job)
    db.flush()
    work_dir = job_output_dir(settings.developability_out_root, name, job.id, job.chains_json)
    work_dir.mkdir(parents=True, exist_ok=True)
    job.work_dir = str(work_dir)
    async_result = dispatch_to_gpu(run_developability_job, job.id)
    job.celery_task_id = async_result.id
    return job
