"""ProteinMPNN sequence design API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.design_service import create_and_queue_design_job, save_uploaded_structure
from app.engines import DESIGN_ENGINE
from app.models import Job, JobStatus, User
from app.schemas import DesignJobCreate, DesignJobListOut, DesignJobOut

router = APIRouter(prefix="/api/design-jobs", tags=["design"])


def _out(job: Job) -> DesignJobOut:
    return DesignJobOut.model_validate(job)


def _params_from_body(body: DesignJobCreate) -> dict:
    return {
        "designed_chains": (body.designed_chains or "").strip(),
        "num_seq_per_target": body.num_seq_per_target,
        "sampling_temp": body.sampling_temp,
        "seed": body.seed,
        "backbone_noise": body.backbone_noise,
        "omit_aas": body.omit_aas or "X",
    }


@router.post("", response_model=DesignJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: DesignJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not body.fold_job_id:
        raise HTTPException(400, "请选择折叠任务，或使用 /upload 上传结构文件")
    name = body.name.strip() if body.name and body.name.strip() else "proteinmpnn"
    job = create_and_queue_design_job(
        db,
        user_id=user.id,
        name=name,
        params=_params_from_body(body),
        fold_job_id=body.fold_job_id,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=DesignJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    structure: UploadFile = File(...),
    name: str | None = Form(default=None),
    designed_chains: str = Form(default=""),
    num_seq_per_target: int = Form(default=8),
    sampling_temp: float = Form(default=0.1),
    seed: int = Form(default=0),
    backbone_noise: float = Form(default=0.0),
    omit_aas: str = Form(default="X"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job_name = name.strip() if name and name.strip() else "proteinmpnn"
    tmp_dir = settings.design_out_root / "_uploads" / user.id
    structure_src = await save_uploaded_structure(structure, tmp_dir)
    params = {
        "designed_chains": (designed_chains or "").strip(),
        "num_seq_per_target": max(1, min(64, int(num_seq_per_target))),
        "sampling_temp": max(0.05, min(1.0, float(sampling_temp))),
        "seed": max(0, int(seed)),
        "backbone_noise": max(0.0, min(1.0, float(backbone_noise))),
        "omit_aas": omit_aas or "X",
    }
    job = create_and_queue_design_job(
        db,
        user_id=user.id,
        name=job_name,
        params=params,
        structure_src=structure_src,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=DesignJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == DESIGN_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return DesignJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=DesignJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != DESIGN_ENGINE:
        raise HTTPException(404, "Design job not found")
    return _out(job)


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != DESIGN_ENGINE:
        raise HTTPException(404, "Design job not found")
    if not job.work_dir or Path(filename).name != filename:
        raise HTTPException(400, "Invalid output filename")
    path = Path(job.work_dir) / filename
    if not path.is_file() or path.parent.resolve() != Path(job.work_dir).resolve():
        raise HTTPException(404, "Output file not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != DESIGN_ENGINE:
        raise HTTPException(404, "Design job not found")
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
