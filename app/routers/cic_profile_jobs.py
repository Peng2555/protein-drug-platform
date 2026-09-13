"""抗体 CIC 表面斑 API。"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.database import get_db
from app.deps import get_current_user
from app.engines import CIC_PROFILE_ENGINE
from app.cic_profile_service import create_and_queue_cic_profile_job, save_structure_upload
from app.models import Job, JobStatus, User
from app.schemas import (
    CicProfileJobCreate,
    CicProfileJobListOut,
    CicProfileJobOut,
    CicProfileProgressOut,
    CicProfileRankedOut,
)

router = APIRouter(prefix="/api/cic-profile-jobs", tags=["cic-profile"])


def _out(job: Job) -> CicProfileJobOut:
    return CicProfileJobOut.model_validate(job)


def _job_or_404(db: Session, user_id: str, job_id: str) -> Job:
    job = db.get(Job, job_id)
    if not job or job.user_id != user_id or job.engine != CIC_PROFILE_ENGINE:
        raise HTTPException(404, "CIC profile job not found")
    return job


def _work(job: Job) -> Path:
    if not job.work_dir:
        raise HTTPException(404, "Job work_dir missing")
    return Path(job.work_dir)


def _exports(job: Job) -> Path:
    return _work(job) / "exports"


@router.post("", response_model=CicProfileJobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    body: CicProfileJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    name = body.name.strip() if body.name and body.name.strip() else "cic_profile"
    job = create_and_queue_cic_profile_job(
        db,
        user_id=user.id,
        name=name,
        fasta_text=body.fasta,
        ph=body.ph,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.post("/upload", response_model=CicProfileJobOut, status_code=status.HTTP_201_CREATED)
async def create_job_upload(
    fasta: str = Form(...),
    name: str | None = Form(default=None),
    ph: float = Form(default=7.0),
    structure: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    structure_path: Path | None = None
    if structure and structure.filename:
        tmp = settings.cic_profile_out_root / "_uploads" / user.id
        suffix = Path(structure.filename).suffix.lower() or ".pdb"
        structure_path = await save_structure_upload(structure, tmp / f"structure{suffix}")
    job_name = name.strip() if name and name.strip() else "cic_profile"
    job = create_and_queue_cic_profile_job(
        db,
        user_id=user.id,
        name=job_name,
        fasta_text=fasta,
        structure_path=structure_path,
        ph=ph,
    )
    db.commit()
    db.refresh(job)
    return _out(job)


@router.get("", response_model=CicProfileJobListOut)
def list_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    condition = (Job.user_id == user.id, Job.engine == CIC_PROFILE_ENGINE)
    rows = db.scalars(
        select(Job).where(*condition).order_by(Job.created_at.desc()).limit(limit).offset(offset)
    ).all()
    total = db.scalar(select(func.count()).select_from(Job).where(*condition)) or 0
    return CicProfileJobListOut(items=[_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=CicProfileJobOut)
def get_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _out(_job_or_404(db, user.id, job_id))


@router.get("/{job_id}/progress", response_model=CicProfileProgressOut)
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
    return CicProfileProgressOut(stage=stage, status=job.status, summary=summary)


@router.get("/{job_id}/ranked", response_model=CicProfileRankedOut)
def get_ranked(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    import csv

    job = _job_or_404(db, user.id, job_id)
    patches: list[dict] = []
    residues: list[dict] = []
    summary = None
    if job.results_json:
        patches = list(job.results_json.get("patches") or [])
        residues = list(job.results_json.get("residues") or [])
        summary = job.results_json.get("summary")
    exports = _exports(job)
    if (exports / "patches.csv").is_file():
        with (exports / "patches.csv").open(newline="", encoding="utf-8") as f:
            patches = list(csv.DictReader(f))
    res_csv = _work(job) / "patches" / "residue_features.csv"
    if not res_csv.is_file():
        res_csv = exports / "residue_features.csv"
    if res_csv.is_file():
        with res_csv.open(newline="", encoding="utf-8") as f:
            residues = list(csv.DictReader(f))
    if (exports / "summary.json").is_file() and summary is None:
        summary = json.loads((exports / "summary.json").read_text(encoding="utf-8"))
    return CicProfileRankedOut(patches=patches, residues=residues, summary=summary)


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
        for alt_dir in (_work(job) / "patches", _work(job) / "fold", _work(job) / "input"):
            alt = alt_dir / filename
            if alt.is_file():
                path = alt
                break
    if not path.is_file():
        raise HTTPException(404, "File not found")
    media = "chemical/x-cif" if path.suffix.lower() == ".cif" else "application/octet-stream"
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
