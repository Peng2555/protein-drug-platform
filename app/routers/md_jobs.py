"""MD simulation job API."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.config import settings
from app.engines import is_fold_engine
from app.database import get_db
from app.deps import get_current_user
from app.job_paths import job_output_dir, remove_job_outputs
from app.md_service import create_and_queue_md_job, resolve_structure_path, save_uploaded_structure
from app.models import Job, JobStatus, User
from app.schemas import MdJobCreate, MdJobListOut, MdJobOut

router = APIRouter(prefix="/api/md-jobs", tags=["md-jobs"])


def _md_job_out(job: Job) -> MdJobOut:
    return MdJobOut.model_validate(job)


@router.post("", response_model=MdJobOut, status_code=status.HTTP_201_CREATED)
def create_md_job(
    body: MdJobCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    parent: Job | None = None
    input_path: Path
    fasta_text = ">md\n."
    chains_json: dict = {"structure": 1}

    if body.parent_job_id:
        parent = db.get(Job, body.parent_job_id)
        if not parent or parent.user_id != user.id:
            raise HTTPException(404, "Parent fold job not found")
        if not is_fold_engine(parent.engine):
            raise HTTPException(400, "Parent job must be a structure prediction job")
        if parent.status != JobStatus.done.value:
            raise HTTPException(409, f"Parent job status: {parent.status}")
        input_path = resolve_structure_path(parent)
        fasta_text = parent.fasta_text
        chains_json = parent.chains_json or chains_json
        name = body.name.strip() if body.name and body.name.strip() else f"md_{parent.name or parent.id[:8]}"
    elif body.structure_path:
        input_path = Path(body.structure_path)
        if not input_path.is_file():
            raise HTTPException(400, "structure_path file not found")
        name = body.name.strip() if body.name and body.name.strip() else f"md_{input_path.stem}"
    else:
        raise HTTPException(400, "Provide parent_job_id or upload structure via /api/md-jobs/upload")

    job = create_and_queue_md_job(
        db,
        user_id=user.id,
        name=name,
        input_structure=input_path,
        parent_job_id=body.parent_job_id,
        fasta_text=fasta_text,
        chains_json=chains_json,
        production_ns=body.production_ns,
        replicas=body.replicas,
        antigen_chain=body.antigen_chain,
        binder_chain=body.binder_chain,
    )
    db.commit()
    db.refresh(job)
    return _md_job_out(job)


@router.post("/upload", response_model=MdJobOut, status_code=status.HTTP_201_CREATED)
async def create_md_job_upload(
    structure: UploadFile = File(...),
    name: str | None = Form(default=None),
    production_ns: float | None = Form(default=None),
    replicas: int | None = Form(default=None),
    antigen_chain: str = Form(default="A"),
    binder_chain: str = Form(default="H"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    tmp_dir = settings.md_out_root / "_uploads" / user.id
    input_path = await save_uploaded_structure(structure, tmp_dir)
    job_name = name.strip() if name and name.strip() else f"md_{input_path.stem}"

    job = create_and_queue_md_job(
        db,
        user_id=user.id,
        name=job_name,
        input_structure=input_path,
        production_ns=production_ns,
        replicas=replicas,
        antigen_chain=antigen_chain,
        binder_chain=binder_chain,
    )
    db.commit()
    db.refresh(job)
    return _md_job_out(job)


@router.post("/from-fold/{fold_job_id}", response_model=MdJobOut, status_code=status.HTTP_201_CREATED)
def create_md_from_fold(
    fold_job_id: str,
    body: MdJobCreate | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    payload = body or MdJobCreate(parent_job_id=fold_job_id)
    payload.parent_job_id = fold_job_id
    return create_md_job(payload, db, user)


@router.get("", response_model=MdJobListOut)
def list_md_jobs(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    q = select(Job).where(Job.user_id == user.id, Job.engine == "gromacs_md")
    count_q = (
        select(func.count())
        .select_from(Job)
        .where(Job.user_id == user.id, Job.engine == "gromacs_md")
    )
    total = db.scalar(count_q) or 0
    rows = db.scalars(q.order_by(Job.created_at.desc()).limit(limit).offset(offset)).all()
    return MdJobListOut(items=[_md_job_out(j) for j in rows], total=total)


@router.get("/{job_id}", response_model=MdJobOut)
def get_md_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != "gromacs_md":
        raise HTTPException(404, "MD job not found")
    return _md_job_out(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_md_job(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != "gromacs_md":
        raise HTTPException(404, "MD job not found")

    if job.status in (JobStatus.queued.value, JobStatus.running.value):
        job.status = JobStatus.cancelled.value
        db.commit()
        if job.celery_task_id:
            celery_app.control.revoke(job.celery_task_id, terminate=True, signal="SIGTERM")

    remove_job_outputs(
        settings.md_out_root,
        job.id,
        job.name,
        job.chains_json,
        job.work_dir,
    )
    db.delete(job)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{job_id}/summary")
def get_md_summary(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != "gromacs_md":
        raise HTTPException(404, "MD job not found")
    if job.results_json:
        return job.results_json
    if job.work_dir:
        summary = Path(job.work_dir) / "04_analysis" / "summary.json"
        if summary.is_file():
            return json.loads(summary.read_text(encoding="utf-8"))
    raise HTTPException(404, "MD summary not available yet")


@router.get("/{job_id}/structure")
def download_md_structure(job_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    job = db.get(Job, job_id)
    if not job or job.user_id != user.id or job.engine != "gromacs_md":
        raise HTTPException(404, "MD job not found")
    if job.status != JobStatus.done.value:
        raise HTTPException(409, f"Job status: {job.status}")

    gro: Path | None = None
    if job.structure_path:
        gro = Path(job.structure_path)
    elif job.work_dir:
        gro = Path(job.work_dir) / "03_prod" / "rep1" / "md.gro"
    if not gro or not gro.is_file():
        raise HTTPException(404, "MD output structure not found")
    return FileResponse(
        gro,
        filename=f"{job.name or job.id}.gro",
        media_type="application/octet-stream",
    )
