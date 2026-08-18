"""RAS tri-complex docking workflow API."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import RAS_DOCKING_ENGINE
from app.models import Job, JobStatus, User
from app.ras_docking_service import (
    create_and_queue_ras_job,
    remove_ras_job_outputs,
    save_candidate_sdf,
)
from app.schemas import RasDockingJobCreate, RasDockingJobListOut, RasDockingJobOut

router = APIRouter(prefix="/api/ras-docking-jobs", tags=["ras-docking"])


def _out(job: Job) -> RasDockingJobOut:
    return RasDockingJobOut.model_validate(job)


def _create(
    body: RasDockingJobCreate,
    db: Session,
    user: User,
    candidate_path: Path | None = None,
) -> RasDockingJobOut:
    if body.project == "rmc6291" and body.stage not in {"download", "prepare", "dock"}:
        raise HTTPException(400, "RMC-6291 当前支持 download、prepare、dock 阶段")
    if body.project == "rmc6236" and body.stage not in {
        "fetch", "prepare", "redock", "screen", "contacts", "literature",
    }:
        raise HTTPException(400, "RMC-6236 阶段无效")
    if body.stage == "screen" and candidate_path is None:
        raise HTTPException(400, "screen 阶段必须上传候选 SDF")
    name = body.name.strip() if body.name and body.name.strip() else (
        f"{body.project}_{body.stage}"
    )
    job = create_and_queue_ras_job(
        db, user_id=user.id, name=name, project=body.project,
        stage=body.stage, system=body.system, candidate_path=candidate_path,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("", response_model=RasDockingJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: RasDockingJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return _create(body, db, user)


@router.post("/screen", response_model=RasDockingJobOut, status_code=status.HTTP_201_CREATED)
async def create_screen_job(
    file: UploadFile = File(...),
    project: str = Form(default="rmc6236"),
    name: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    candidate_path = await save_candidate_sdf(file, user.id)
    body = RasDockingJobCreate(name=name, project=project, stage="screen")
    return _create(body, db, user, candidate_path)


@router.get("", response_model=RasDockingJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == RAS_DOCKING_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc())
        .limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return RasDockingJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=RasDockingJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != RAS_DOCKING_ENGINE:
        raise HTTPException(404, "RAS docking job not found")
    return _out(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != RAS_DOCKING_ENGINE:
        raise HTTPException(404, "RAS docking job not found")
    if job.status in (JobStatus.queued.value, JobStatus.running.value):
        job.status = JobStatus.cancelled.value
        db.commit()
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")
    remove_ras_job_outputs(job)
    db.delete(job)
    db.commit()
