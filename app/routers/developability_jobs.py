"""ESM-2 antibody developability redesign API."""

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
from app.developability_service import create_and_queue_developability_job, save_uploaded_structure
from app.engines import DEVELOPABILITY_ENGINE
from app.models import Job, JobStatus, User
from app.schemas import (
    DevelopabilityJobCreate,
    DevelopabilityJobListOut,
    DevelopabilityJobOut,
)

router = APIRouter(prefix="/api/developability-jobs", tags=["developability"])


def _out(job: Job) -> DevelopabilityJobOut:
    return DevelopabilityJobOut.model_validate(job)


@router.post("", response_model=DevelopabilityJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: DevelopabilityJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fasta = body.fasta.strip()
    name = body.name.strip() if body.name and body.name.strip() else "developability"
    params = {
        "goal": body.goal,
        "freeze_cysteine": body.freeze_cysteine,
        "freeze_cdr3": body.freeze_cdr3,
        "freeze_all_cdrs": body.freeze_all_cdrs,
        "dll_threshold": body.dll_threshold,
        "max_mutants_per_site": body.max_mutants_per_site,
        "run_maxwell": body.run_maxwell,
    }
    job = create_and_queue_developability_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=fasta,
        params=params,
        fold_job_id=body.fold_job_id,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=DevelopabilityJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    structure: UploadFile = File(...),
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    goal: str = Form(default="both"),
    freeze_cysteine: bool = Form(default=True),
    freeze_cdr3: bool = Form(default=True),
    freeze_all_cdrs: bool = Form(default=False),
    dll_threshold: float = Form(default=0.0),
    max_mutants_per_site: int = Form(default=19),
    run_maxwell: bool = Form(default=True),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fasta_text = fasta.strip()
    job_name = name.strip() if name and name.strip() else "developability"
    tmp_dir = settings.developability_out_root / "_uploads" / user.id
    structure_src = await save_uploaded_structure(structure, tmp_dir)
    params = {
        "goal": goal if goal in {"hydro", "tm", "both"} else "both",
        "freeze_cysteine": freeze_cysteine,
        "freeze_cdr3": freeze_cdr3,
        "freeze_all_cdrs": freeze_all_cdrs,
        "dll_threshold": dll_threshold,
        "max_mutants_per_site": max_mutants_per_site,
        "run_maxwell": run_maxwell,
    }
    job = create_and_queue_developability_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta_text,
        params=params,
        structure_src=structure_src,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=DevelopabilityJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == DEVELOPABILITY_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return DevelopabilityJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=DevelopabilityJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != DEVELOPABILITY_ENGINE:
        raise HTTPException(404, "Developability job not found")
    return _out(job)


@router.post("/{job_id}/resubmit", response_model=DevelopabilityJobOut, status_code=status.HTTP_201_CREATED)
def resubmit_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    src = db.get(Job, job_id)
    if not src or src.user_id != user.id or src.engine != DEVELOPABILITY_ENGINE:
        raise HTTPException(404, "Developability job not found")
    if not src.fasta_text or not src.fasta_text.strip():
        raise HTTPException(400, "原任务没有可复用的 FASTA")
    src_params = src.params_json or {}
    params = {
        "goal": src_params.get("goal", "both"),
        "freeze_cysteine": bool(src_params.get("freeze_cysteine", True)),
        "freeze_cdr3": bool(src_params.get("freeze_cdr3", True)),
        "freeze_all_cdrs": bool(src_params.get("freeze_all_cdrs", False)),
        "dll_threshold": float(src_params.get("dll_threshold", 0.0)),
        "max_mutants_per_site": int(src_params.get("max_mutants_per_site", 19)),
        "run_maxwell": bool(src_params.get("run_maxwell", True)),
    }
    name = src.name or "developability"
    structure_src = Path(src.structure_path) if src.structure_path and Path(src.structure_path).is_file() else None
    fold_job_id = src_params.get("fold_job_id")
    if not isinstance(fold_job_id, str) or not fold_job_id or structure_src:
        fold_job_id = None
    job = create_and_queue_developability_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=src.fasta_text,
        params=params,
        structure_src=structure_src,
        fold_job_id=fold_job_id,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != DEVELOPABILITY_ENGINE:
        raise HTTPException(404, "Developability job not found")
    if not job.work_dir or Path(filename).name != filename:
        raise HTTPException(400, "Invalid output filename")
    path = Path(job.work_dir) / filename
    if not path.is_file() or path.parent.resolve() != Path(job.work_dir).resolve():
        raise HTTPException(404, "Output file not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != DEVELOPABILITY_ENGINE:
        raise HTTPException(404, "Developability job not found")
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
