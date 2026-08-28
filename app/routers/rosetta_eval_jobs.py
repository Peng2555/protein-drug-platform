"""Rosetta antibody–antigen evaluation API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.database import get_db
from app.deps import get_current_user
from app.engines import ROSETTA_EVAL_ENGINE
from app.models import Job, JobStatus, User
from app.rosetta_eval_service import (
    _fold_variant,
    create_and_queue_rosetta_eval_job,
    save_upload,
)
from app.schemas import RosettaEvalJobCreate, RosettaEvalJobListOut, RosettaEvalJobOut

router = APIRouter(prefix="/api/rosetta-eval-jobs", tags=["rosetta-eval"])


def _out(job: Job) -> RosettaEvalJobOut:
    return RosettaEvalJobOut.model_validate(job)


@router.post("", response_model=RosettaEvalJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: RosettaEvalJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not body.wt_fold_job_id:
        raise HTTPException(400, "请选择 WT 折叠任务，或使用 /upload 上传结构")
    if not body.mutant_fold_job_ids:
        raise HTTPException(400, "请至少选择一个突变体折叠任务")
    variants = [_fold_variant(db, user.id, body.wt_fold_job_id, is_wt=True)]
    for job_id in body.mutant_fold_job_ids:
        if job_id == body.wt_fold_job_id:
            continue
        variants.append(_fold_variant(db, user.id, job_id, is_wt=False))
    name = body.name.strip() if body.name and body.name.strip() else "rosetta_eval"
    job = create_and_queue_rosetta_eval_job(
        db,
        user_id=user.id,
        name=name,
        parent_job_id=body.wt_fold_job_id,
        variants=variants,
        params={
            "nstruct": max(1, min(10, int(body.nstruct))),
            "n_jobs": max(1, min(64, int(body.n_jobs))),
            "antibody_chains": (body.antibody_chains or "").strip(),
            "antigen_chains": (body.antigen_chains or "").strip(),
        },
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=RosettaEvalJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    wt: UploadFile = File(...),
    mutants: list[UploadFile] = File(...),
    name: str | None = Form(default=None),
    nstruct: int = Form(default=3),
    n_jobs: int = Form(default=16),
    antibody_chains: str = Form(default=""),
    antigen_chains: str = Form(default=""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not mutants:
        raise HTTPException(400, "请上传至少一个突变体结构")
    from app.config import settings

    tmp = settings.rosetta_eval_out_root / "_uploads" / user.id
    wt_path = await save_upload(wt, tmp / f"WT{Path(wt.filename or '.pdb').suffix.lower()}")
    variants = [{"name": "WT", "path": str(wt_path), "is_wt": True}]
    for i, upload in enumerate(mutants, start=1):
        dest = await save_upload(
            upload,
            tmp / f"mutant_{i:03d}{Path(upload.filename or '.pdb').suffix.lower()}",
        )
        variants.append(
            {
                "name": Path(upload.filename or dest.stem).stem,
                "path": str(dest),
                "is_wt": False,
            }
        )
    job_name = name.strip() if name and name.strip() else "rosetta_eval"
    job = create_and_queue_rosetta_eval_job(
        db,
        user_id=user.id,
        name=job_name,
        variants=variants,
        params={
            "nstruct": max(1, min(10, int(nstruct))),
            "n_jobs": max(1, min(64, int(n_jobs))),
            "antibody_chains": (antibody_chains or "").strip(),
            "antigen_chains": (antigen_chains or "").strip(),
        },
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=RosettaEvalJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == ROSETTA_EVAL_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return RosettaEvalJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=RosettaEvalJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != ROSETTA_EVAL_ENGINE:
        raise HTTPException(404, "Rosetta eval job not found")
    return _out(job)


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != ROSETTA_EVAL_ENGINE:
        raise HTTPException(404, "Rosetta eval job not found")
    if not job.work_dir or Path(filename).name != filename:
        raise HTTPException(400, "Invalid output filename")
    path = Path(job.work_dir) / filename
    if not path.is_file() or path.parent.resolve() != Path(job.work_dir).resolve():
        raise HTTPException(404, "Output file not found")
    return FileResponse(path, filename=filename, media_type="application/octet-stream")


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != ROSETTA_EVAL_ENGINE:
        raise HTTPException(404, "Rosetta eval job not found")
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
