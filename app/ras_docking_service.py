"""RAS tri-complex docking job creation and result helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import settings
from app.engines import RAS_DOCKING_ENGINE
from app.job_paths import job_output_dir
from app.models import Job, JobStatus
from app.queue_service import dispatch_to_gpu
from worker.tasks import run_ras_docking_job


def create_and_queue_ras_job(
    db: Session,
    *,
    user_id: str,
    name: str,
    project: str,
    stage: str,
    system: str = "rmc6291",
    candidate_path: Path | None = None,
) -> Job:
    params = {
        "project": project,
        "stage": stage,
        "system": system,
    }
    if candidate_path:
        params["candidate_path"] = str(candidate_path)

    job = Job(
        user_id=user_id,
        name=name,
        engine=RAS_DOCKING_ENGINE,
        status=JobStatus.queued.value,
        stage="queued",
        fasta_text=">ras_docking\n.",
        sequence_hash="ras-tricomplex",
        chains_json={"KRAS": 1, "CypA": 1, "ligand": 1},
        total_length=3,
        use_msa_server=False,
        params_json=params,
    )
    db.add(job)
    db.flush()
    job.work_dir = str(job_output_dir(
        settings.ras_docking_out_root, name, job.id, job.chains_json,
    ))
    async_result = dispatch_to_gpu(run_ras_docking_job, job.id)
    job.celery_task_id = async_result.id
    return job


async def save_candidate_sdf(upload: UploadFile, user_id: str) -> Path:
    filename = Path(upload.filename or "candidates.sdf")
    if filename.suffix.lower() not in {".sdf", ".sd", ".mol"}:
        raise HTTPException(400, "候选分子文件必须是 SDF/MOL 格式")
    dest_dir = settings.ras_docking_out_root / "_uploads" / user_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "candidates.sdf"
    content = await upload.read()
    if len(content) < 20:
        raise HTTPException(400, "候选分子文件为空或过小")
    dest.write_bytes(content)
    return dest


def remove_ras_job_outputs(job: Job) -> None:
    if job.work_dir:
        shutil.rmtree(job.work_dir, ignore_errors=True)
