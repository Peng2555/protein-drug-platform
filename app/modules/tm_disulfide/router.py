"""抗体额外二硫键 API。"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.celery import celery_app
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.engines import TM_DISULFIDE_ENGINE
from app.core.models import Job, JobStatus, User
from app.modules.tm_disulfide.service import (
    create_and_queue_tm_disulfide_job,
    list_source_fold_jobs,
)
from app.schemas import (
    TmDisulfideJobCreate,
    TmDisulfideJobListOut,
    TmDisulfideJobOut,
    TmDisulfideProgressOut,
    TmDisulfideRankedOut,
    TmDisulfideSourceFoldJobListOut,
    TmDisulfideSourceFoldJobOut,
)

router = APIRouter(prefix="/api/tm-disulfide-jobs", tags=["tm-disulfide"])


def _out(job: Job) -> TmDisulfideJobOut:
    return TmDisulfideJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != TM_DISULFIDE_ENGINE:
        raise HTTPException(404, "Tm disulfide job not found")
    return job


def _work(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir)


def _exports(job: Job) -> Path:
    return _work(job) / "exports"


@router.post("", response_model=TmDisulfideJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: TmDisulfideJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip() if body.name and body.name.strip() else "tm_disulfide"
    job = create_and_queue_tm_disulfide_job(
        db,
        user_id=user.id,
        name=name,
        source_job_id=body.source_job_id.strip(),
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=TmDisulfideJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == TM_DISULFIDE_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return TmDisulfideJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/source-fold-jobs", response_model=TmDisulfideSourceFoldJobListOut)
def list_source_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
):
    rows = list_source_fold_jobs(db, user.id, limit=limit)
    items = [
        TmDisulfideSourceFoldJobOut(
            id=job.id,
            name=job.name,
            status=job.status,
            n_models=n_models,
            total_length=job.total_length,
            created_at=job.created_at,
        )
        for job, n_models in rows
    ]
    return TmDisulfideSourceFoldJobListOut(items=items, total=len(items))


@router.get("/{job_id}", response_model=TmDisulfideJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/progress", response_model=TmDisulfideProgressOut)
def get_progress(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    stage = job.stage or "queued"
    summary = None
    if job.work_dir:
        wf = Path(job.work_dir) / "workflow_status.json"
        if wf.is_file():
            try:
                data = json.loads(wf.read_text(encoding="utf-8"))
                stage = str(data.get("stage") or stage)
                summary = data.get("summary")
            except json.JSONDecodeError:
                pass
    return TmDisulfideProgressOut(stage=stage, status=job.status, summary=summary)


@router.get("/{job_id}/ranked", response_model=TmDisulfideRankedOut)
def get_ranked(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    candidates: list[dict] = []
    summary = None
    if job.results_json:
        summary = job.results_json.get("summary")
    exports = _exports(job)
    csv_path = exports / "candidates.csv"
    if csv_path.is_file():
        with csv_path.open(newline="", encoding="utf-8") as handle:
            candidates = list(csv.DictReader(handle))
    if (exports / "summary.json").is_file() and summary is None:
        summary = json.loads((exports / "summary.json").read_text(encoding="utf-8"))
    return TmDisulfideRankedOut(candidates=candidates, summary=summary)


@router.get("/{job_id}/files/{filename}")
def download_file(
    job_id: str,
    filename: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    job = _job_or_404(db, user.id, job_id)
    if Path(filename).name != filename or ".." in filename:
        raise HTTPException(400, "Invalid filename")
    path = _exports(job) / filename
    if not path.is_file():
        for alt_dir in (_work(job) / "input", _work(job) / "energy", _work(job) / "build"):
            alt = alt_dir / filename
            if alt.is_file():
                path = alt
                break
    if not path.is_file():
        raise HTTPException(404, "File not found")
    media = "application/octet-stream"
    if path.suffix.lower() == ".csv":
        media = "text/csv; charset=utf-8"
    if path.suffix.lower() == ".json":
        media = "application/json"
    return FileResponse(path, filename=filename, media_type=media)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = _job_or_404(db, user.id, job_id)
    if job.status in (JobStatus.queued.value, JobStatus.running.value) and job.celery_task_id:
        celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    db.delete(job)
    db.commit()
